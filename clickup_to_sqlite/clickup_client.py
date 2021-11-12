"""
This is a clickup client library, which is more than what we might need for the
sqlite export.

However this hasn't been extracted to another library yet. So I keep it here for
personal use.
"""
import json
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from itertools import count
from typing import Any, Callable, Iterable, Iterator, List, Optional, TypeVar, Union

import httpx
from loguru import logger
from pydantic import BaseModel, validator

T = TypeVar("T")


class User(BaseModel):
    id: int
    username: Optional[str]
    email: str
    color: Optional[str]
    initials: str
    profilePicture: Optional[str]


class UserContainer(BaseModel):
    user: User


class Team(BaseModel):
    id: str
    name: str
    color: str
    members: List[UserContainer]


class Teams(BaseModel):
    teams: List[Team]


class Status(BaseModel):
    status: str
    type: str
    orderindex: int
    color: str


class Space(BaseModel):
    id: str
    name: str
    private: bool
    statuses: List[Status]  # TODO
    features: dict


class Spaces(BaseModel):
    spaces: List[Space]


class DropDownOption(BaseModel):
    id: str
    name: str
    color: Optional[str]
    orderindex: int


class DropDownTypeConfig(BaseModel):
    default: int
    placeholder: Optional[str]
    options: List[DropDownOption]

    def get_option_for_value(self, value: int) -> DropDownOption:
        selected = [o for o in self.options if o.orderindex == value]
        if not selected:
            raise ValueError(
                f"No value of {value!r} in drop down, valid values are: {[o.orderindex for o in self.options]}"
            )
        assert len(selected) == 1
        return selected[0]


class CustomFieldDefinition(BaseModel):
    id: str
    name: str
    type: str
    type_config: dict

    def get_type_config(self):
        if self.type == "drop_down":
            return DropDownTypeConfig(**self.type_config)
        raise ValueError(f"Unknown type: {self.type}")


class CustomFieldValue(BaseModel):
    id: str
    name: str
    type: str
    type_config: dict
    date_created: Optional[str]  # TODO
    hide_from_guests: bool
    value: Optional[Union[int, str]]
    required: bool

    def get_type_config(self):
        if self.type == "drop_down":
            return DropDownTypeConfig(**self.type_config)
        raise ValueError(f"Unknown type: {self.type}")


class TaskList(BaseModel):
    id: str
    name: str
    access: bool


class IdElement(BaseModel):
    id: str


class Priority(BaseModel):
    id: str
    priority: str
    color: str
    orderindex: int


class Task(BaseModel):
    id: str
    custom_id: Optional[str]
    name: str
    description: Optional[str]
    status: Status
    orderindex: float
    date_created: str  # TODO
    date_updated: str  # TODO
    date_closed: Optional[str]  # TODO
    archived: bool
    creator: dict  # TODO
    assignees: List[dict]  # TODO
    tags: list  # TODO
    parent: Optional[str]
    priority: Optional[Priority]
    due_date: Optional[str]  # TODO
    start_date: Optional[str]  # TODO
    points: Optional[float]
    # In milliseconds
    time_estimate: Optional[int]
    # In milliseconds
    # UNDOCUMENTED
    time_spent: Optional[int]
    custom_fields: List[CustomFieldValue]
    dependencies: List[Any]  # TODO
    linked_tasks: List[Any]  # TODO
    team_id: str
    url: str
    permission_level: str
    list: TaskList
    project: IdElement
    folder: IdElement
    space: IdElement


class Tasks(BaseModel):
    tasks: List[Task]


class TimeEntryTaskStatus(BaseModel):
    status: str
    color: str
    type: str
    orderindex: float


class TimeEntryTask(BaseModel):
    id: str
    name: str
    status: TimeEntryTaskStatus
    custom_type: Optional[str]


class timedelta_ms(timedelta):
    @classmethod
    def __get_validators__(cls):
        # one or more validators may be yielded which will be called in the
        # order to validate the input, each validator will receive as an input
        # the value returned from the previous validator
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, str):
            v = int(v)
        if not isinstance(v, int):
            raise TypeError(f"int required, got {type(v)} for {v}")
        return cls(milliseconds=v)


class TimeEntry(BaseModel):
    id: str
    task: Optional[TimeEntryTask]
    wid: str
    user: User
    billable: bool
    start: datetime
    end: datetime
    duration: timedelta_ms
    description: str
    tags: List[str]
    source: str
    at: datetime

    @validator("task", pre=True)
    def allow_no_task(cls, v):
        if v == "0":
            return None
        return v


class TimeEntries(BaseModel):
    data: List[TimeEntry]


class Client:
    """
    API docs are at https://clickup.com/api

    Get the token from ClickUp at "Settings > My Apps > Apps > API Token".
    """

    def __init__(self, token: str):
        self._token = token

    @contextmanager
    def _client(self) -> Iterator[httpx.Client]:
        client = httpx.Client(headers=self._get_headers(), base_url=self._get_url(""))
        with client as c:
            yield c

    def _get_headers(self):
        return {"Authorization": self._token}

    def _get_url(self, path: str) -> str:
        return f"https://app.clickup.com/api/v2/{path}"

    def _request(self, method: str, path: str, params=None, **kwargs) -> dict:
        with self._client() as client:
            logger.debug(f"{method} {path} ? {params}")
            response = client.request(method, path, params=params, **kwargs)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                logger.error(
                    f"HTTP {error.response.status_code}: {error.response.text}"
                )
            return response.json()

    def get(self, path: str, params: Optional[dict] = None):
        encode_value = (
            lambda value: value if isinstance(value, str) else json.dumps(value)
        )
        params = params or {}
        params = {key: encode_value(value) for key, value in params.items()}
        return self._request("GET", path, params=params)

    def get_raw(
        self, path: str, params: Optional[dict] = None, pop_toplevel: bool = True
    ):
        """
        ``pop_toplevel``: If ``True``, then we assume that the response is a
        JSON object with exactly one key at the toplevel. This is the norm for
        clickup responses. E.g. ``{"tasks": [...]}``.
        """

        def pop_toplevel_key(data: dict):
            keys = list(data.keys())
            assert (
                len(keys) == 1
            ), f"Expected exactly one key at toplevel of response, got {keys}"
            return data.pop(keys[0])

        return self._cast(
            lambda data: pop_toplevel_key(data) if pop_toplevel else data,
            self.get(path, params=params),
        )

    def post(self, path: str, data: dict, params: Optional[dict] = None):
        encode_value = (
            lambda value: value if isinstance(value, str) else json.dumps(value)
        )
        params = params or {}
        params = {key: encode_value(value) for key, value in params.items()}
        return self._request("POST", path, params=params, json=data)

    def put(self, path: str, data: dict, params: Optional[dict] = None):
        encode_value = (
            lambda value: value if isinstance(value, str) else json.dumps(value)
        )
        params = params or {}
        params = {key: encode_value(value) for key, value in params.items()}
        return self._request("PUT", path, params=params, json=data)

    def _cast(self, cast_type: Callable[[Any], T], data) -> T:
        try:
            return cast_type(data)
        except Exception:
            from io import StringIO
            from pprint import pprint

            stream = StringIO()
            pprint(data, stream=stream)
            stream.seek(0)
            logger.error(f"Got error response:\n{stream.read(500)}")
            raise

    def get_teams(self) -> List[Team]:
        return self._cast(lambda data: Teams(**data).teams, self.get("team"))

    def get_spaces(self, team_id: str, archived: bool = False) -> List[Space]:
        return self._cast(
            lambda data: Spaces(**data).spaces,
            self.get(f"team/{team_id}/space", {"archived": archived}),
        )

    def get_folders_raw(self, space_id: str, archived: bool = False) -> List[dict]:
        return self.get_raw(f"space/{space_id}/folder", {"archived": archived})

    def get_folderless_lists_raw(
        self, space_id: str, archived: bool = False
    ) -> List[dict]:
        return self.get_raw(f"space/{space_id}/list", {"archived": archived})

    def get_task(self, task_id: str, include_subtasks: bool = False) -> Task:
        return self._cast(
            lambda data: Task(**data),
            self.get(
                f"task/{task_id}/",
                {**({"include_subtasks": "1"} if include_subtasks else {})},
            ),
        )

    def get_filtered_team_tasks(self, team_id: str, params: dict) -> Iterable[Task]:
        for page in count(start=0):
            params = {
                **params,
                "page": page,
            }
            tasks = self._cast(
                lambda data: Tasks(**data).tasks,
                self.get(f"team/{team_id}/task", params=params),
            )
            if len(tasks) == 0:
                return
            yield from tasks

    def get_view_tasks(self, view_id: str) -> Iterable[Task]:
        for page in count(start=0):
            params = {
                "page": page,
            }
            data = self.get(f"view/{view_id}/task", params=params)
            yield from self._cast(lambda data: Tasks(**data).tasks, data)
            if data["last_page"]:
                return

    def update_task(self, task_id: str, data) -> Task:
        return self._cast(
            lambda data: Task(**data), self.put(f"task/{task_id}", data=data)
        )

    def set_custom_field_value(self, task_id: str, field_id: str, value: Any) -> None:
        self.post(f"task/{task_id}/field/{field_id}/", data={"value": value})

    # Time Tracking 2.0

    def get_time_entries_within_a_date_range(
        self,
        team_id: str,
        start_date: datetime,
        end_date: datetime,
        assignee: Optional[int] = None,
    ):
        assignee_opts = {"assignee": assignee} if assignee is not None else {}
        return self._cast(
            lambda data: TimeEntries(**data).data,
            self.get(
                f"team/{team_id}/time_entries",
                {
                    "start_date": self.datetime_to_posix(start_date),
                    "end_date": self.datetime_to_posix(end_date),
                    **assignee_opts,
                },
            ),
        )

    @classmethod
    def datetime_to_posix(cls, dt: Union[date, datetime]) -> str:
        if isinstance(dt, date):
            dt = datetime(year=dt.year, month=dt.month, day=dt.day)
        return str(int(dt.timestamp() * 1000))

    @classmethod
    def timestamp_to_datetime(cls, timestamp: str) -> datetime:
        timestamp_int = int(timestamp)
        return datetime.fromtimestamp(timestamp_int / 1000)
