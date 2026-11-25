from typing import Annotated

from pydantic import BaseModel, ConfigDict, FiniteFloat, StringConstraints

# 带编号的单个拍点：beat 为相对样板序列的拍号，time 为实播时间（秒）
class PlayBeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    beat: int
    time: FiniteFloat


class ReportSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    routing: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    segment: int
    beats: list[PlayBeat]
