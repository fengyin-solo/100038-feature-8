"""逆变器管理业务规则：状态流转、字段校验与筛选口径都收在这里。

效率视图所需的近七天转换效率序列也由本模块给出：序列按设备编号做确定性
生成，服务重启后数据不漂移，便于班组持续观察是哪几台在拖后腿。
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "inverter"
REQUIRED_FIELDS = ["设备编号", "设备型号", "额定功率"]
STATUS_ORDER = ["待调试", "运行中", "故障停机", "已退役"]
ACTION_RULES = {"完成调试": "运行中", "登记故障": "故障停机", "退役设备": "已退役"}
NEGATIVE_ACTIONS = ["登记故障", "退役设备"]

# 列表/面板共用的检索字段：前端按中文名提交，后端这里统一解释。
FILTER_FIELDS = ["设备编号", "设备型号", "额定功率", "所属方阵", "运行状态"]
# 转换效率的额定区间（含端点），低于下限即视为拖后腿，需要高亮。
RATED_MIN = 95.0
RATED_MAX = 98.5
# 面板均值与列表登记值允许的偏差（百分点），超过即判为对不上。
AVG_TOLERANCE = 0.5
SERIES_DAYS = 7
_PERCENT_RE = re.compile(r"-?\d+(?:\.\d+)?")

# 每台设备的效率曲线画像：base/spread 决定近七天均值与波动，
# missing 表示近七天完全没采到数据，gaps 表示部分日期缺测。
# 部分设备刻意让列表登记值与曲线均值偏差超过 AVG_TOLERANCE，
# 用来提示“面板效率与列表平均值对不上”。
EFFICIENCY_PROFILES: dict[str, dict[str, Any]] = {
    "INV-0101": {"missing": True, "reason": "设备待调试，尚未开始效率采集"},
    "INV-0102": {"base": 97.6, "spread": 0.4},
    "INV-0103": {"base": 93.7, "spread": 0.5},
    "INV-0201": {"base": 98.1, "spread": 0.3},
    "INV-0202": {"base": 95.4, "spread": 0.55},
    "INV-0301": {"base": 95.9, "spread": 0.4, "gaps": {3, 4, 5, 6}},
    "INV-0302": {"base": 96.9, "spread": 0.4},
    "INV-0303": {"missing": True, "reason": "通讯中断，近七天无效率数据回传"},
}


def _parse_percent(value: Any) -> float | None:
    """把“97.8%”这类登记值解析成数值；解析不出来时返回 None，不猜默认值。"""
    if value is None:
        return None
    match = _PERCENT_RE.search(str(value))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _jitter(code: str, day_index: int) -> float:
    """按设备编号与天序生成 [-1, 1] 的稳定抖动，重启后结果一致。"""
    digest = hashlib.md5(f"{code}:{day_index}".encode("utf-8")).digest()
    return (digest[0] / 255.0) * 2.0 - 1.0


class InverterService:
    # ---- 列表与动作：保持原有口径，仅把筛选字段放开 ----------------------

    def list_entries(
        self,
        *,
        filters: dict[str, str] | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._apply_filters(store.rows(MODULE), filters or {})
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"逆变器 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于逆变器管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"逆变器已{action}"

    # ---- 近七天转换效率视图 ---------------------------------------------

    def efficiency_overview(
        self,
        *,
        filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """按与列表相同的条件取设备，组装近七天效率曲线数据。

        采不到数据的设备进 missing_devices；曲线均值与列表登记值对不上
        的设备在条目标 mismatch=True，由前端单独标出。
        """
        rows = self._apply_filters(store.rows(MODULE), filters or {})
        rows.sort(key=lambda row: str(row.get("设备编号", "")))

        today = date.today()
        days = [(today - timedelta(days=SERIES_DAYS - 1 - i)).isoformat()
                for i in range(SERIES_DAYS)]

        devices: list[dict[str, Any]] = []
        missing_devices: list[dict[str, Any]] = []
        below_count = 0
        mismatch_count = 0

        for row in rows:
            code = str(row.get("设备编号", ""))
            base_info = {
                "id": row.get("id"),
                "code": code,
                "array": row.get("所属方阵") or "未归属方阵",
                "model": row.get("设备型号") or "",
                "status": row.get("运行状态") or row.get("status") or "",
            }
            profile = EFFICIENCY_PROFILES.get(code)
            if profile is None:
                # 未配置画像的设备：登记值可解析就按登记值给稳定曲线，
                # 否则一律归入“采不到数据”，不能把效率显示成正常。
                listed = _parse_percent(row.get("转换效率"))
                if listed is None:
                    missing_devices.append({
                        **base_info,
                        "reason": "缺少效率采集配置",
                    })
                    continue
                profile = {"base": listed, "spread": 0.3}

            if profile.get("missing"):
                missing_devices.append({
                    **base_info,
                    "reason": str(profile.get("reason") or "近七天未采集到效率数据"),
                })
                continue

            values = self._build_series(code, profile, days)
            present = [item["value"] for item in values if item["value"] is not None]
            if not present:
                missing_devices.append({
                    **base_info,
                    "reason": "近七天效率数据全部缺测",
                })
                continue

            average = round(sum(present) / len(present), 2)
            listed_avg = _parse_percent(row.get("转换效率"))
            mismatch = (
                listed_avg is not None
                and abs(average - listed_avg) > AVG_TOLERANCE
            )
            below_rated = average < RATED_MIN
            if below_rated:
                below_count += 1
            if mismatch:
                mismatch_count += 1

            devices.append({
                **base_info,
                "days": days,
                "series": values,
                "average": average,
                "listed_avg": listed_avg,
                "below_rated": below_rated,
                "mismatch": mismatch,
                "present_days": len(present),
            })

        return {
            "days": days,
            "rated_min": RATED_MIN,
            "rated_max": RATED_MAX,
            "avg_tolerance": AVG_TOLERANCE,
            "total": len(rows),
            "devices": devices,
            "missing_devices": missing_devices,
            "below_count": below_count,
            "mismatch_count": mismatch_count,
        }

    def _build_series(
        self,
        code: str,
        profile: dict[str, Any],
        days: list[str],
    ) -> list[dict[str, Any]]:
        base = float(profile["base"])
        spread = float(profile.get("spread", 0.4))
        gaps: set[int] = set(profile.get("gaps", set()))
        series: list[dict[str, Any]] = []
        for index, day in enumerate(days):
            if index in gaps:
                series.append({"date": day, "value": None})
                continue
            wave = 0.15 * (1 if index % 2 == 0 else -1)
            value = round(base + spread * _jitter(code, index) + wave, 2)
            series.append({"date": day, "value": value})
        return series

    def _apply_filters(
        self,
        rows: list[dict[str, Any]],
        filters: dict[str, str],
    ) -> list[dict[str, Any]]:
        """解释列表与效率面板共用的查询条件；未知字段忽略，不影响原列表。"""
        result = rows
        for field, raw in filters.items():
            keyword = str(raw or "").strip()
            if not keyword or field not in FILTER_FIELDS:
                continue
            if field == "运行状态":
                result = [
                    row for row in result
                    if keyword in str(row.get("运行状态") or row.get("status") or "")
                ]
            else:
                result = [
                    row for row in result
                    if keyword in str(row.get(field) or "")
                ]
        return result
