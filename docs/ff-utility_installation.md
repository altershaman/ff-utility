# Managing installation

## Prerequisites

- **git** — BB storage is git-based. Must be available in `PATH`.
- **Python 3.10+** — required to run `ff`.
- **ollama** — required for suggestion mechanism when quering concepts and judgments. 


## ff installing
```bash
git clone https://github.com/altershaman/ff-utility.git
cd ff-utility
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```
Now `ff` is available in any directory (while the venv is active).

## ff uninstalling

```bash
deactivate
rm -rf .venv
```

## Installing and running ollama

Some `ff` commands generate vector embeddings. These require **ollama** to be installed and running with a compatible embedding model.

#### 1. Install ollama

Download and install from [ollama.com](https://ollama.com). On Linux:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### 2. Start ollama

On macOS and Windows, ollama starts automatically after installation. On Linux, you may need to start it manually or configure it as a service.

```bash
ollama serve
```

If `ollama serve` fails because port 11434 is already in use, check what is holding it:

```bash
lsof -i :11434
```
or
```bash
ss -tlnp | grep 11434
```
If the output shows `ollama` — it is already running. Nothing else to do.

#### 3. Pull the embedding model

```bash
ollama pull nomic-embed-text
```
`nomic-embed-text` is the default embedding model. A different model can be set globally in `~/.config/ff/config` or per BB at `ff init` time.

This is the default model (~274MB). It runs on CPU and requires no GPU.

#### 4. Verify

```bash
ollama list
```

`nomic-embed-text` should appear in the output.

#### 5. Using a different model

Set a global default in `~/.config/ff/config`:

```json
{
  "embedding_model": "all-minilm"
}
```

Or override per BB by specifying the model at `ff init` time. The model is locked once the first embedding is written — changing it afterwards requires reindexing.
