import os
from typing import Optional

import click
from sqlite_utils import Database

from .clickup_client import Client, Task


def fetch_teams(db: Database, client: Client) -> None:
    teams = client.get_teams()

    teams_dict = []
    members_dict = []
    for team in teams:
        team_json = team.dict()
        for member in team_json.pop("members"):
            members_dict.append({"team_id": team_json["id"], **member["user"]})
        teams_dict.append(team_json)

    db["teams"].insert_all(teams_dict, pk="id")
    db["members"].insert_all(members_dict, pk="id")
    db["members"].add_foreign_key("team_id", "teams", "id")


def fetch_spaces(db: Database, client: Client) -> None:
    team_ids = [r["id"] for r in db.query("SELECT id FROM teams")]
    space_dicts = []
    for team_id in team_ids:
        spaces = client.get_spaces(team_id)
        for space in spaces:
            space_dicts.append(space.dict())
    db["spaces"].insert_all(space_dicts, pk="id")


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

    init_folders = not db["folders"].exists()
    init_lists = not db["lists"].exists()

    db["folders"].insert_all(folders, pk="id")
    if init_folders:
        db["folders"].add_foreign_key("space_id", "spaces", "id")

    db["lists"].insert_all(lists, pk="id")
    if init_lists:
        db["lists"].add_foreign_key("folder_id", "folders", "id")
        db["lists"].add_foreign_key("space_id", "spaces", "id")


def fetch_tasks(db: Database, client: Client, team_id: str) -> None:
    tasks = list(client.get_filtered_team_tasks(team_id, {"include_closed": True, "subtasks": True}))

    def format_task(task: Task) -> dict:
        task_dict = task.dict(exclude={"list", "project", "folder", "space"})
        task_dict.update({
            "list_id": task.list.id,
            "project_id": task.project.id,
            "folder_id": task.folder.id,
            "space_id": task.space.id,
        })
        return task_dict

    task_dicts = [format_task(t) for t in tasks]

    init_tasks = not db["tasks"].exists()
    db["tasks"].insert_all(task_dicts, pk="id")
    if init_tasks:
        db["tasks"].add_foreign_key("list_id", "lists", "id")
        db["tasks"].add_foreign_key("folder_id", "folders", "id")
        db["tasks"].add_foreign_key("space_id", "spaces", "id")
        db["tasks"].add_foreign_key("team_id", "teams", "id")


@click.group()
def cli():
    pass


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
def fetch(db_path: str):
    # TODO: Make this available via some auth flow.
    # For now copy from ClickUp at "Settings > My Apps > Apps > API Token".
    token = os.environ["CLICKUP_ACCESS_TOKEN"]
    client = Client(token)
    db = Database(db_path)

    fetch_teams(db, client)
    fetch_spaces(db, client)

    team_ids = [r["id"] for r in db.query("SELECT id FROM teams")]
    space_ids = [r["id"] for r in db.query("SELECT id FROM spaces")]
    for space_id in space_ids:
        fetch_folders_and_lists(db, client, space_id=space_id)

    for team_id in team_ids:
        fetch_tasks(db, client, team_id=team_id)
