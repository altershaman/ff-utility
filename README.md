# ff-utility
Core Fractality Framework cli utility managing Bounded Beliefs

## Installation

```bash
git clone <repo-url>
cd ff-utility
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

After installation run `source <path/to/installation/directory>.venv/bin/activate` in terminal window, then `ff` is available in any directory (while the venv is active).

## Usage

### `ff init`

Initializes a Bounded Belief store in the current directory.

```
ff init
```

- If the directory is not under git, you will be asked whether to initialize a git repository. Answering `n` exits without creating anything.
- If a BB store already exists, prints its title and description and exits.
- Otherwise, prompts for a title and description (both optional — press Enter to skip), then creates the store.

The BB store is kept entirely inside `.git/` and does not add any files to your working tree.

## Uninstallation

```bash
deactivate
rm -rf .venv
```
