"""逆变器管理业务规则：状态流转、字段校验、筛选口径与近七天转换效率视图。"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "inverter"
REQUIRED_FIELDS = ["设备编号", "设备型号", "额定功率"]
STATUS_ORDER = ["待调试", "运行中", "故障停机", "已退役"]
ACTION_RULES = {"完成调试": "运行中", "登记故障": "故障停机", "退役设备": "已退役"}
NEGATIVE_ACTIONS = []

# 各型号的额定转换效率区间（%）；不在型号表里的设备统一按通用区间兜底。
RATED_EFFICIENCY_BANDS: dict[str, tuple[float, float]] = {
    "SG250HX": (97.2, 98.4),
    "KSG-312K": (97.0, 98.2),
}
DEFAULT_RATED_BAND = (97.0, 98.4)

# 近七天转换效率采集值（%），按逆变器 id 对齐；None 表示当天采集缺测，
# 完全不在这里登记的设备视为采数通道未覆盖（新设备/通讯未接入）。
# id=2、id=5 是持续低效的拖后腿设备；id=6 后半段掉出额定区间；id=7 只有零星缺测数据。
EFFICIENCY_TELEMETRY: dict[int, list[float | None]] = {
    1: [98.0, 98.1, 97.8, 98.2, 98.0, 97.9, 98.1],
    2: [95.2, 94.9, 95.4, 94.6, 94.8, 94.5, 94.2],
    3: [97.6, 97.7, 97.5, 97.8, 97.6, 97.4, 97.7],
    4: [98.1, 98.0, 98.2, 97.9, 98.3, 98.0, 97.8],
    5: [94.0, 93.8, 94.1, 93.5, 93.7, 93.2, 93.6],
    6: [98.2, 98.0, 98.1, 98.3, 97.9, 94.7, 93.9],
    7: [None, None, None, None, 96.1, None, None],
}

# 面板均值与列表均值对不上时，允许的偏差（百分点）。
MEAN_MISMATCH_TOLERANCE = 0.5


def _rated_band(model: Any) -> tuple[float, float]:
    return RATED_EFFICIENCY_BANDS.get(str(model or "").strip(), DEFAULT_RATED_BAND)


def parse_efficiency(value: Any) -> float | None:
    """把列表里的「转换效率」解析成百分数数值（如 97.9）。

    空、—、非数值都返回 None；兼容 0.98 与 98.0 两种登记口径。
    """
    if value is None:
        return None
    text = str(value).strip().replace("％", "%")
    if not text or text in {"—", "-", "--"}:
        return None
    text = text.removesuffix("%").strip()
    try:
        number = float(text)
    except ValueError:
        return None
    return round(number * 100 if 0 < number <= 1 else number, 2)


class InverterService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        device_model: str | None = None,
        rated_power: str | None = None,
        entry_ids: list[int] | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if entry_ids is not None:
            rows = [row for row in rows if int(row.get("id", 0)) in entry_ids]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        # 列表筛选区里的设备型号、额定功率条件：做子串匹配，空条件不拦截。
        if device_model:
            rows = [row for row in rows if device_model in str(row.get("设备型号", ""))]
        if rated_power:
            rows = [row for row in rows if rated_power in str(row.get("额定功率", ""))]
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

    def efficiency_overview(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        device_model: str | None = None,
        rated_power: str | None = None,
        entry_ids: list[int] | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """效率视图面板数据：按当前列表的同一套条件取设备，再挂接近七天采集曲线。

        - 采集通道没覆盖、或七天全缺测的设备进 missing，绝不当作正常效率展示；
        - 低于所属型号额定区间的天数会标记 low_days，供面板高亮并标出方阵；
        - 面板均值与列表登记值对不上时在 mismatch 里说明，口径差异要让班组看见。
        """
        rows, _ = self.list_entries(
            keyword=keyword,
            status=status,
            device_model=device_model,
            rated_power=rated_power,
            entry_ids=entry_ids,
            page=1,
            size=10000,
        )
        days = max(1, min(days, 30))
        end_day = date.today()
        labels = [(end_day - timedelta(days=days - 1 - offset)).isoformat() for offset in range(days)]

        devices: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for row in sorted(rows, key=lambda item: str(item.get("设备编号", ""))):
            entry_id = int(row.get("id", 0))
            base = {
                "id": entry_id,
                "设备编号": row.get("设备编号", ""),
                "设备型号": row.get("设备型号", ""),
                "所属方阵": row.get("所属方阵", ""),
                "运行状态": row.get("运行状态", row.get("status", "")),
            }
            series_full = EFFICIENCY_TELEMETRY.get(entry_id)
            if series_full is None:
                missing.append({**base, "reason": "效率采集通道未接入"})
                continue
            series = [self._normalize_point(point) for point in series_full[-days:]]
            if not any(point is not None for point in series):
                missing.append({**base, "reason": "近七天效率数据全部缺测"})
                continue

            low, high = _rated_band(row.get("设备型号"))
            valid_points = [point for point in series if point is not None]
            mean = round(sum(valid_points) / len(valid_points), 2)
            list_value = parse_efficiency(row.get("转换效率"))
            mismatch = list_value is not None and abs(mean - list_value) > MEAN_MISMATCH_TOLERANCE
            devices.append({
                **base,
                "series": series,
                "mean": mean,
                "list_efficiency": list_value,
                "rated_lower": low,
                "rated_upper": high,
                "low_days": [labels[i] for i, point in enumerate(series) if point is not None and point < low],
                "mismatch": mismatch,
            })

        return {
            "days": days,
            "labels": labels,
            "rated_bands": [
                {"model": model, "lower": low, "upper": high}
                for model, (low, high) in sorted(RATED_EFFICIENCY_BANDS.items())
            ],
            "devices": devices,
            "missing": missing,
        }

    @staticmethod
    def _normalize_point(point: float | None) -> float | None:
        if point is None:
            return None
        return round(float(point), 2)
