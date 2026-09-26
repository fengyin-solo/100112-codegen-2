"""冷藏箱温控巡检业务规则：判定口径、字段校验、温度记录去重都收在这里。

判定口径只有一条：箱温低于下限或高于上限即标记超温，超温时长 = 超温记录数 × 巡检频次；
未超温但距上限不足 WARNING_MARGIN 的记为预警。列表、详情、统计都从温度记录实时推导，
刷新后超温数量与详情里的温度记录自然一致。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "reefer"
REQUIRED_FIELDS = ["箱号", "设定温度", "温度下限", "温度上限", "巡检频次"]
NUMERIC_FIELDS = ["设定温度", "温度下限", "温度上限", "巡检频次"]
STATUS_ORDER = ["待巡检", "巡检中", "已办结"]
ACTION_RULES = {"开始巡检": "巡检中", "结束巡检": "已办结"}
ACTION_GUARD = {"开始巡检": "待巡检", "结束巡检": "巡检中"}
WARNING_MARGIN = 1.0  # 预警带宽（℃）：箱温距上限不足 1℃ 即视为接近上限


def _to_float(value: Any) -> float | None:
    """把输入转成浮点数；None、空串、非数值一律按缺失处理。"""
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_number(value: float) -> int | float:
    """整数值按 int 存，避免页面上出现 30.0 这样的频次。"""
    return int(value) if float(value).is_integer() else value


def _validate_settings(values: dict[str, Any]) -> list[str]:
    """登记前的拦检：箱温缺失、区间填反等问题在这里一次性说清楚。"""
    problems: list[str] = []
    if not str(values.get("箱号") or "").strip():
        problems.append("箱号缺失")
    numbers: dict[str, float] = {}
    for field in NUMERIC_FIELDS:
        raw = values.get(field)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            problems.append(f"{field}缺失")
            continue
        number = _to_float(raw)
        if number is None:
            problems.append(f"{field}不是有效数值")
            continue
        numbers[field] = number
    if "温度下限" in numbers and "温度上限" in numbers and numbers["温度下限"] > numbers["温度上限"]:
        problems.append(f"温度区间填反：下限 {numbers['温度下限']}℃ 高于上限 {numbers['温度上限']}℃")
    if "巡检频次" in numbers and numbers["巡检频次"] <= 0:
        problems.append("巡检频次必须大于 0 分钟")
    return problems


def _validate_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """逐条校验温度记录：记录时间与箱温缺一不可，箱温必须是数值。"""
    cleaned: list[dict[str, Any]] = []
    problems: list[str] = []
    for index, item in enumerate(records, start=1):
        moment = str(item.get("记录时间") or "").strip()
        temp = _to_float(item.get("温度"))
        if not moment:
            problems.append(f"第 {index} 条温度记录缺少记录时间")
        if temp is None:
            problems.append(f"第 {index} 条温度记录的箱温缺失或不是数值")
        if moment and temp is not None:
            cleaned.append({"记录时间": moment, "温度": temp})
    return cleaned, problems


def _judge(temp: float, lower: float, upper: float) -> str:
    """唯一判定口径：超出区间即超温，未超温但接近上限给预警。"""
    if temp < lower or temp > upper:
        return "超温"
    if temp >= upper - WARNING_MARGIN:
        return "预警"
    return "正常"


class ReeferService:
    def evaluate(self, entry: dict[str, Any]) -> dict[str, Any]:
        """从温度记录实时推导判定结果，列表与详情共用这一份，保证刷新后一致。"""
        lower = float(entry.get("温度下限"))
        upper = float(entry.get("温度上限"))
        frequency = float(entry.get("巡检频次"))
        records: list[dict[str, Any]] = []
        over_count = 0
        warned = False
        for record in entry.get("records", []):
            verdict = _judge(float(record["温度"]), lower, upper)
            over_count += verdict == "超温"
            warned = warned or verdict == "预警"
            records.append({**record, "判定": verdict})
        over_minutes = _to_number(over_count * frequency)
        return {
            "records": records,
            "温度记录数": len(records),
            "超温记录数": over_count,
            "超温时长（分钟）": over_minutes,
            "预警": "是" if warned else "否",
            "最新温度": records[-1]["温度"] if records else None,
        }

    def serialize(self, entry: dict[str, Any], *, with_records: bool = False) -> dict[str, Any]:
        derived = self.evaluate(entry)
        row = {key: value for key, value in entry.items() if key != "records"}
        row["巡检状态"] = entry.get("status")
        row["温度区间"] = f"{entry.get('温度下限')} ~ {entry.get('温度上限')} ℃"
        row.update({key: value for key, value in derived.items() if key != "records"})
        if with_records:
            row["records"] = derived["records"]
        return row

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("箱号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self.serialize(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self.serialize(entry, with_records=True)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        problems = _validate_settings(values)
        if problems:
            return None, problems
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["箱号"] = str(values["箱号"]).strip()
        for field in NUMERIC_FIELDS:
            entry[field] = _to_number(float(values[field]))
        entry["巡检人"] = str(values.get("巡检人") or "").strip() or "未指派"
        entry["登记时间"] = str(values.get("登记时间") or "").strip() or date.today().isoformat()
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["records"] = []
        rows.append(entry)  # 校验全部通过后才落库，中断重来不会留下半条记录
        return self.serialize(entry, with_records=True), []

    def add_records(self, entry_id: int, records: Any) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"冷藏箱巡检 {entry_id} 不存在或已归档"
        if entry.get("status") != "巡检中":
            return None, f"箱号 {entry.get('箱号')} 当前为「{entry.get('status')}」，需先开始巡检再录入温度"
        if not isinstance(records, list) or not records:
            return None, "本次没有需要保存的温度记录"
        cleaned, problems = _validate_records(records)
        if problems:
            return None, "；".join(problems)
        # 先在副本上按时段合并，全部校验通过后才替换，巡检中断重报不会留下半条记录
        merged = {record["记录时间"]: dict(record) for record in entry.get("records", [])}
        before = len(merged)
        for record in cleaned:
            merged[record["记录时间"]] = record  # 同一时段重复只留一条，以最新上报为准
        entry["records"] = sorted(merged.values(), key=lambda record: record["记录时间"])
        entry["abnormal"] = self.evaluate(entry)["超温记录数"] > 0
        message = f"已保存 {len(cleaned)} 条温度记录"
        if before + len(cleaned) - len(merged) > 0:
            message += "，同一时段的重复记录已合并为一条"
        return self.serialize(entry, with_records=True), message

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"冷藏箱巡检 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于冷藏箱温控巡检可执行范围"
        expected = ACTION_GUARD[action]
        if entry.get("status") != expected:
            return None, f"当前状态为「{entry.get('status')}」，不能执行「{action}」"
        entry["status"] = ACTION_RULES[action]
        entry["pending"] = entry["status"] != STATUS_ORDER[-1]
        return self.serialize(entry, with_records=True), f"冷藏箱巡检已{action}"
