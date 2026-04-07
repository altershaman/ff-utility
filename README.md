# ff-utility
Core Fractality Framework cli utility managing Bounded Beliefs

## Prerequisites

- **git** — BB storage is git-based. Must be available in `PATH`.
- **Python 3.10+** — required to run `ff`.
- **ollama** — required for `ff suggest`. Install from [ollama.com](https://ollama.com), then pull an embedding model:
  ```bash
  ollama pull nomic-embed-text
  ```
  `nomic-embed-text` is the default embedding model. A different model can be set globally in `~/.config/ff/config` or per BB at `ff init` time.

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

### `ff concept` — working with concepts

All concept operations share the same command:

```
ff concept <content> [options]
ff -c <content> [options]
```

`<content>` is either a path to a markdown file or a quoted string.

#### Suggest

```
ff concept 'engine powertrain'
ff concept file.md
```

Returns existing concepts from BB ranked by semantic similarity to the input. Requires ollama.

#### Genesis

```
ff concept file.md --genesis
ff concept '# Engine\n...' --genesis
```

Records content as a new concept in BB. Assigns a UUID and extracts the title from the highest-level markdown heading. Requires ollama.

#### New version

```
ff concept file.md --uuid <uuid>
ff concept file.md -a <alias>
```

Records content as a new version of an existing concept. Version history is kept in git. Requires ollama.

#### Resolve

```
ff concept --uuid <uuid>
ff concept -a <alias>
```

Returns the latest version of a concept from BB. Does not require ollama.

#### Aliases and UUID input

Suggest output assigns short aliases (`a`, `b`, `c`, ...) to each result. These are saved in `.git/bb/aliases.json` and persist until the next suggest.

```
ff concept 'engine'
# 0.92  a  a3f7cd47-...  # Engine
# 0.87  b  b2c12de9-...  # Motor
```

Use `-a`/`--alias` to reference a concept by its alias in the next command:

```
ff concept -a b                   # resolve Motor
ff concept file.md -a b           # new version of Motor
```

Use `--uuid` to reference by full UUID or any unambiguous prefix:

```
ff concept --uuid b2c12de9        # resolve by prefix
ff concept --uuid b2c12de9-0577-4115-a62e-f2a3a5c783b7  # resolve by full UUID
```

#### Output flags

| Flag | Effect |
|---|---|
| `--json` | Structured JSON output |
| `--md` | Write concept content as `.md` files to the current directory |
| `--full` | Return full content instead of excerpt (applies to suggest and resolve) |

---

### `ff suggest` and embedding operations

Some `ff` operations generate vector embeddings — specifically `suggest` and `genesis`. These require **ollama** to be installed and running with a compatible embedding model.

#### 1. Install ollama

Download and install from [ollama.com](https://ollama.com). On Linux:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### 2. Start ollama

```bash
ollama serve
```

On macOS and Windows, ollama starts automatically after installation. On Linux, you may need to start it manually or configure it as a service.

If `ollama serve` fails because port 11434 is already in use, check what is holding it:

```bash
lsof -i :11434
```

If the output shows `ollama` — it is already running. Nothing else to do.


#### 3. Pull the embedding model

```bash
ollama pull nomic-embed-text
```

This is the default model (~274MB). It runs on CPU and requires no GPU.

#### 4. Verify

```bash
ollama list
```

`nomic-embed-text` should appear in the output.

#### Using a different model

Set a global default in `~/.config/ff/config`:

```json
{
  "embedding_model": "all-minilm"
}
```

Or override per BB by specifying the model at `ff init` time. The model is locked once the first embedding is written — changing it afterwards requires reindexing.


#### Which commands require ollama

| Command | Requires ollama |
|---|---|
| `ff init` | No |
| `ff resolve` | No |
| `ff genesis` | Yes |
| `ff new-version` | Yes |
| `ff suggest` | Yes |

If ollama is not reachable or the model is not pulled, `ff` will print a clear error before attempting any operation.

## Uninstallation

```bash
deactivate
rm -rf .venv
```
