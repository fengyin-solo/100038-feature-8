"""逆变器管理接口：维护逆变器，覆盖完成调试、登记故障、退役设备等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.inverter import InverterService

router = APIRouter(prefix="/api/inverter", tags=["逆变器管理"])

service = InverterService()

LIST_FIELDS = ["设备编号", "设备型号", "额定功率", "转换效率", "所属方阵", "通讯地址", "投运日期", "运行状态"]
STATUSES = ["待调试", "运行中", "故障停机", "已退役"]


def _resolve_filter_args(
    keyword: str | None,
    status: str | None,
    device_model: str | None,
    rated_power: str | None,
) -> dict[str, str | None]:
    """汇总列表过滤参数；设备编号同时接受 keyword 与中文名两种口径。"""
    return {
        "keyword": keyword,
        "status": status,
        "device_model": device_model,
        "rated_power": rated_power,
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按设备编号检索"),
    status: str | None = Query(default=None, description="待调试、运行中、故障停机、已退役"),
    设备编号: str | None = Query(default=None, description="按设备编号检索（与 keyword 等价）"),
    设备型号: str | None = Query(default=None, description="按设备型号子串筛选"),
    额定功率: str | None = Query(default=None, description="按额定功率子串筛选"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按设备编号与状态过滤逆变器管理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    filters = _resolve_filter_args(keyword or 设备编号, status, 设备型号, 额定功率)
    items, total = service.list_entries(**filters, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/efficiency-overview")
def efficiency_overview(
    keyword: str | None = Query(default=None, description="按设备编号检索"),
    status: str | None = Query(default=None, description="待调试、运行中、故障停机、已退役"),
    设备编号: str | None = Query(default=None, description="按设备编号检索（与 keyword 等价）"),
    设备型号: str | None = Query(default=None, description="按设备型号子串筛选"),
    额定功率: str | None = Query(default=None, description="按额定功率子串筛选"),
    ids: str | None = Query(default=None, description="限定设备 id 列表，逗号分隔；与列表当前页对齐"),
    days: int = Query(default=7, ge=1, le=30, description="效率曲线天数，默认近七天"),
) -> dict[str, Any]:
    """效率视图面板：与列表同一套筛选口径，返回近七天转换效率曲线与缺采设备清单。"""
    entry_ids: list[int] | None = None
    if ids:
        try:
            entry_ids = [int(part) for part in ids.split(",") if part.strip()]
        except ValueError as error:
            raise HTTPException(status_code=400, detail="ids 必须是逗号分隔的设备 id") from error
    filters = _resolve_filter_args(keyword or 设备编号, status, 设备型号, 额定功率)
    return service.efficiency_overview(**filters, entry_ids=entry_ids, days=days)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出逆变器管理清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "inverter", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条逆变器明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"逆变器 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条逆变器，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="逆变器已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条逆变器执行完成调试、登记故障、退役设备；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
