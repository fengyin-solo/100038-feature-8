"""逆变器管理接口：维护逆变器，覆盖完成调试、登记故障、退役设备等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.inverter import FILTER_FIELDS, InverterService

router = APIRouter(prefix="/api/inverter", tags=["逆变器管理"])

service = InverterService()

LIST_FIELDS = ["设备编号", "设备型号", "额定功率", "转换效率", "所属方阵", "通讯地址", "投运日期", "运行状态"]
STATUSES = ["待调试", "运行中", "故障停机", "已退役"]


def _extract_filters(request: Request) -> dict[str, str]:
    """从查询串里取列表支持的中文字段；同名参数取最后一个。"""
    return {
        field: values[-1]
        for field in FILTER_FIELDS
        if (values := request.query_params.getlist(field))
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    request: Request,
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按设备编号、设备型号、额定功率等条件过滤逆变器列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(filters=_extract_filters(request), page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/efficiency")
def efficiency_overview(request: Request) -> dict[str, Any]:
    """近七天转换效率视图：过滤口径与列表完全一致，列表条件变化时曲线同步更新。

    devices 为采到数据的设备（含曲线、均值、是否低于额定区间、是否与列表
    登记值对不上）；missing_devices 为没采到效率数据的设备，单独列出。
    """
    return service.efficiency_overview(filters=_extract_filters(request))


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
