import os
from datetime import datetime
from typing import Optional

import click
from sqlite_utils import Database

from .clickup_client import Client, Task, TimeEntry


def fetch_teams(db: Database, client: Client) -> None:
    teams = client.get_teams()

    teams_dict = []
    members_dict = []
    for team in teams:
        team_json = team.dict()
        for member in team_json.pop("members"):
            members_dict.append({"team_id": team_json["id"], **member["user"]})
        teams_dict.append(team_json)

    db["teams"].insert_all(teams_dict, pk="id", replace=True)
    db["members"].insert_all(members_dict, pk="id", replace=True)
    db["members"].add_foreign_key("team_id", "teams", "id", ignore=True)


def fetch_spaces(db: Database, client: Client) -> None:
    team_ids = [r["id"] for r in db.query("SELECT id FROM teams")]
    space_dicts = []
    for team_id in team_ids:
        spaces = client.get_spaces(team_id)
        for space in spaces:
            space_dicts.append(space.dict())
    db["spaces"].insert_all(space_dicts, pk="id", replace=True)


def fetch_folders_and_lists(db: Database, client: Client, space_id: str) -> None:
    folder_dicts = client.get_folders_raw(space_id)
    folders = []
    lists = []

    def format_list(list_dict: dict, folder_id: Optional[str] = None) -> dict:
        if "folder" in list_dict and list_dict["folder"]:
            list_dict["folder_id"] = list_dict.pop("folder")["id"]
        else:
            list_dict["folder_id"] = None
        list_dict["space_id"] = list_dict.pop("space")["id"]
        return list_dict

    for folder_dict in folder_dicts:
        folder_dict["space_id"] = folder_dict.pop("space")["id"]
        list_dicts = folder_dict.pop("lists")
        lists.extend(
            format_list(list_dict, folder_dict["id"]) for list_dict in list_dicts
        )
        folders.append(folder_dict)

    folderless_list_dicts = client.get_folderless_lists_raw(space_id)
    for list_dict in folderless_list_dicts:
        lists.append(format_list(list_dict))

    db["folders"].insert_all(folders, pk="id", replace=True)
    db["folders"].add_foreign_key("space_id", "spaces", "id", ignore=True)

    db["lists"].insert_all(lists, pk="id", replace=True)
    db["lists"].add_foreign_key("folder_id", "folders", "id", ignore=True)
    db["lists"].add_foreign_key("space_id", "spaces", "id", ignore=True)


def fetch_tasks(db: Database, client: Client, team_id: str) -> None:
    tasks = list(
        client.get_filtered_team_tasks(
            team_id, {"include_closed": True, "subtasks": True}
        )
    )

    def format_task(task: Task) -> dict:
        task_dict = task.dict(exclude={"list", "project", "folder", "space"})
        task_dict.update(
            {
                "list_id": task.list.id,
                "project_id": task.project.id,
                "folder_id": task.folder.id,
                "space_id": task.space.id,
            }
        )
        return task_dict

    task_dicts = [format_task(t) for t in tasks]

    db["tasks"].insert_all(task_dicts, pk="id", replace=True)
    db["tasks"].add_foreign_key("list_id", "lists", "id", ignore=True)
    db["tasks"].add_foreign_key("folder_id", "folders", "id", ignore=True)
    db["tasks"].add_foreign_key("space_id", "spaces", "id", ignore=True)
    db["tasks"].add_foreign_key("team_id", "teams", "id", ignore=True)


def fetch_time_entries(
    db: Database, client: Client, team_id: str, start_date: datetime, end_date: datetime
) -> None:
    time_entries = list(
        client.get_time_entries_within_a_date_range(
            team_id, start_date=start_date, end_date=end_date
        )
    )

    def format_time_entries(time: TimeEntry) -> dict:
        time_dict = time.dict(exclude={"task", "user", "duration"})
        time_dict.update(
            {
                "team_id": team_id,
                "user_id": time.user.id,
                "task_id": time.task.id if time.task is not None else None,
                "duration": time.duration.total_seconds(),
            }
        )
        return time_dict

    time_dicts = [format_time_entries(t) for t in time_entries]

    db["timeentries"].insert_all(time_dicts, pk="id", replace=True)
    db["timeentries"].add_foreign_key("task_id", "tasks", "id", ignore=True)
    db["timeentries"].add_foreign_key("user_id", "members", "id", ignore=True)
    db["timeentries"].add_foreign_key("team_id", "teams", "id", ignore=True)


@click.group()
def cli():
    pass


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
@click.option(
    "--access-token",
    envvar="CLICKUP_ACCESS_TOKEN",
    help=(
        "Your personal access token. Retrieve from ClickUp at "
        "'Settings > My Apps > Apps > API Token'. Will read from "
        "CLICKUP_ACCESS_TOKEN environment variable."
    ),
)
def fetch(db_path: str, access_token: str):
    """
    Fetch data from clickup and store into DB_PATH. If the database already
    exists, then entries will be updated.

    Entries that have been deleted from clickup will not be removed from the
    database though.
    """
    # TODO: Make this available via some auth flow.
    client = Client(access_token)
    db = Database(db_path)

    fetch_teams(db, client)
    fetch_spaces(db, client)

    team_ids = [r["id"] for r in db.query("SELECT id FROM teams")]
    space_ids = [r["id"] for r in db.query("SELECT id FROM spaces")]
    for space_id in space_ids:
        fetch_folders_and_lists(db, client, space_id=space_id)

    for team_id in team_ids:
        fetch_tasks(db, client, team_id=team_id)

    now = datetime.utcnow()
    start_date = now.replace(year=now.year - 10)
    end_date = now.replace(year=now.year + 10)

    for team_id in team_ids:
        fetch_time_entries(
            db, client, team_id=team_id, start_date=start_date, end_date=end_date
        )
