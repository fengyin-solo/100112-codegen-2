"""冷藏箱温控巡检业务规则：温度区间、巡检频次、超温判定口径与记录合并都收在这里。

判定口径只有一条（judge）：箱温超出 [温度下限, 温度上限] 即标记超温；
未超温但距上限 1℃ 以内给出接近上限预警；其余正常。列表、详情、汇总全部
从温度记录实时推导，不另存计数，刷新后超温数量与详情记录自然一致。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.store import store

MODULE = "reefer"
REQUIRED_FIELDS = ["箱号", "温度下限", "温度上限", "巡检频次(小时)", "箱温"]
STATUSES = ["正常", "预警", "超温"]
WARN_GAP = 1.0  # 距温度上限 1℃ 以内视为接近上限，给出预警
TIME_FORMATS = ["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]


def judge(temp: float, low: float, high: float) -> str:
    """唯一判定口径：超出区间即超温；贴近上限预警；其余正常。"""
    if temp < low or temp > high:
        return "超温"
    if high - temp <= WARN_GAP:
        return "预警"
    return "正常"


def _to_float(raw: Any) -> float | None:
    try:
        return round(float(str(raw).strip()), 1)
    except (TypeError, ValueError):
        return None


def _parse_time(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _fmt(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")


def _normalize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """温度记录按时间排序；同一时段重复的记录只留一条（以最后提交的为准）。"""
    by_time: dict[str, dict[str, Any]] = {}
    for rec in records:
        moment = _parse_time(rec.get("记录时间"))
        temp = _to_float(rec.get("箱温"))
        if moment is None or temp is None:
            continue
        key = _fmt(moment)
        by_time[key] = {"记录时间": key, "箱温": temp}
    return [by_time[key] for key in sorted(by_time)]


def _overtemp_hours(records: list[dict[str, Any]], low: float, high: float) -> float:
    """当前这次超温的持续时间：取记录末尾连续超温的一段，首尾时间差即持续小时数。"""
    run_start: datetime | None = None
    run_end: datetime | None = None
    for rec in records:
        moment = _parse_time(rec["记录时间"])
        if moment is None:
            continue
        if judge(float(rec["箱温"]), low, high) == "超温":
            if run_start is None:
                run_start = moment
            run_end = moment
        else:
            run_start = None
            run_end = None
    if run_start is None or run_end is None:
        return 0.0
    return round((run_end - run_start).total_seconds() / 3600, 1)


def _decorate(entry: dict[str, Any], *, with_records: bool = False) -> dict[str, Any]:
    """从温度记录实时推导展示字段：判定结果、超温持续、超温记录数，保证各处口径一致。"""
    low = _to_float(entry.get("温度下限")) or 0.0
    high = _to_float(entry.get("温度上限")) or 0.0
    freq = _to_float(entry.get("巡检频次(小时)")) or 0.0
    records = _normalize(list(entry.get("温度记录") or []))
    latest = records[-1] if records else None
    temp = latest["箱温"] if latest else None
    verdict = judge(float(temp), low, high) if temp is not None else "待巡检"
    last_moment = _parse_time(latest["记录时间"]) if latest else None
    row: dict[str, Any] = {
        "id": entry.get("id"),
        "箱号": entry.get("箱号"),
        "温度下限": low,
        "温度上限": high,
        "巡检频次(小时)": freq,
        "当前箱温": temp,
        "判定结果": verdict,
        "超温持续(小时)": _overtemp_hours(records, low, high) if verdict == "超温" else 0.0,
        "超温记录数": sum(1 for rec in records if judge(float(rec["箱温"]), low, high) == "超温"),
        "上次巡检时间": latest["记录时间"] if latest else None,
        "下次巡检时间": _fmt(last_moment + timedelta(hours=freq)) if last_moment and freq > 0 else None,
        "巡检人": entry.get("巡检人"),
        "status": verdict,
        "pending": verdict != "正常",
        "abnormal": verdict == "超温",
    }
    if with_records:
        row["温度记录"] = [
            {**rec, "判定": judge(float(rec["箱温"]), low, high)} for rec in records
        ]
    return row


def _refresh_flags(entry: dict[str, Any]) -> None:
    """写入后同步概览用的状态标记，让运营概览的超温量与明细口径一致。"""
    view = _decorate(entry)
    entry["status"] = view["status"]
    entry["pending"] = view["pending"]
    entry["abnormal"] = view["abnormal"]


class ReeferService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        views = [_decorate(entry) for entry in store.rows(MODULE)]
        if keyword:
            views = [row for row in views if keyword in str(row.get("箱号", ""))]
        if status:
            views = [row for row in views if row.get("判定结果") == status]
        total = len(views)
        start = max(page - 1, 0) * size
        return views[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return _decorate(entry, with_records=True)

    def summary(self) -> dict[str, int]:
        views = [_decorate(entry) for entry in store.rows(MODULE)]
        return {
            "在港冷藏箱": len(views),
            "超温箱量": sum(1 for row in views if row["判定结果"] == "超温"),
            "预警箱量": sum(1 for row in views if row["判定结果"] == "预警"),
            "正常箱量": sum(1 for row in views if row["判定结果"] == "正常"),
        }

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}，已拦下未保存"
        low = _to_float(values.get("温度下限"))
        high = _to_float(values.get("温度上限"))
        if low is None or high is None:
            return None, "温度下限、温度上限都要填数字，已拦下未保存"
        if low > high:
            return None, f"温度区间填反了：下限 {low}℃ 高于上限 {high}℃，已拦下未保存"
        freq = _to_float(values.get("巡检频次(小时)"))
        if freq is None or freq <= 0:
            return None, "巡检频次要是大于 0 的数字（单位：小时），已拦下未保存"
        temp = _to_float(values.get("箱温"))
        if temp is None:
            return None, "箱温缺失或不是数字，已拦下未保存"
        moment = _parse_time(values.get("记录时间")) or datetime.now()
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "箱号": str(values.get("箱号")).strip(),
            "温度下限": low,
            "温度上限": high,
            "巡检频次(小时)": freq,
            "巡检人": str(values.get("巡检人") or "").strip() or "值班员",
            "温度记录": [{"记录时间": _fmt(moment), "箱温": temp}],
        }
        _refresh_flags(entry)
        rows.append(entry)
        return _decorate(entry, with_records=True), "冷藏箱已登记，首条温度记录已入库"

    def submit_readings(
        self,
        entry_id: int,
        readings: list[dict[str, Any]],
        inspector: str,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"冷藏箱 {entry_id} 不存在或已离场"
        if not readings:
            return None, "本次巡检没有提交温度记录，未保存"
        # 先整批校验：任何一条不合格都整批拦下，巡检中断重来不会留下半批记录
        parsed: list[dict[str, Any]] = []
        for index, raw in enumerate(readings, 1):
            temp = _to_float(raw.get("箱温"))
            if temp is None:
                return None, f"第 {index} 条温度记录缺少箱温（或不是数字），整批已拦下未保存"
            moment = _parse_time(raw.get("记录时间"))
            if moment is None:
                return None, f"第 {index} 条温度记录的时间缺失或格式不对（YYYY-MM-DD HH:MM），整批已拦下未保存"
            parsed.append({"记录时间": _fmt(moment), "箱温": temp})
        # 校验全部通过才合并落库：同一时段只留一条，重复提交结果不变
        before = len(_normalize(list(entry.get("温度记录") or [])))
        merged = _normalize(list(entry.get("温度记录") or []) + parsed)
        duplicates = len(parsed) - (len(merged) - before)
        entry["温度记录"] = merged
        if inspector:
            entry["巡检人"] = inspector
        _refresh_flags(entry)
        view = _decorate(entry, with_records=True)
        message = f"已保存 {len(parsed)} 条温度记录"
        if duplicates:
            message += f"，其中 {duplicates} 条重复时段已合并只留一条"
        message += f"；当前判定：{view['判定结果']}"
        if view["判定结果"] == "超温":
            message += f"，已持续 {view['超温持续(小时)']} 小时"
        return view, message
