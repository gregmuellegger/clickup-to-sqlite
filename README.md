# clickup-to-sqlite

[![PyPI](https://img.shields.io/pypi/v/clickup-to-sqlite.svg)](https://pypi.org/project/clickup-to-sqlite/)
[![Changelog](https://img.shields.io/github/v/release/gregmuellegger/clickup-to-sqlite?include_prereleases&label=changelog)](https://github.com/gregmuellegger/clickup-to-sqlite/releases)
[![Tests](https://github.com/gregmuellegger/clickup-to-sqlite/workflows/Test/badge.svg)](https://github.com/gregmuellegger/clickup-to-sqlite/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/gregmuellegger/clickup-to-sqlite/blob/main/LICENSE)

Save data from [ClickUp](https://clickup.com/) to a SQLite database.

Currently to CLI tool collects the following data from ClickUp:

- Teams
- Spaces
- Lists
- Folders
- Tasks
- Time entries

The following data is currently not yet downloaded:

- Comments
- Goals
- Guests
- Member data
- Views

## How to install

```
$ pip install clickup-to-sqlite
```

## Authentication

First, you will need to get your personal access token from ClickUp. Retrieve it
from ClickUp under         _Settings > My Apps > Apps > API Token_. Then use the
value with the `--auth-token` option like explained below or provide it with the
`CLICKUP_ACCESS_TOKEN` environment variable. This works especially well when
using something like [direnv](https://direnv.net/).

## Usage

To download your ClickUp data into a sqlite database run the following command:

```
$ clickup-to-sqlite fetch --auth-token=pk_YOUR_PERSONAL_TOKEN clickup.sqlite
```

Note: Currently the data fetching will run into the rate limit applied by the
ClickUp API if your backlog of tasks or time entries is rather large.

Once you have downloaded the data into the sqlite database, you can explore the
data. I recommend to have a look at [Datasette](https://datasette.io/) for adhoc
analysis.
