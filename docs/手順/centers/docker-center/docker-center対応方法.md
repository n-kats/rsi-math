# docker-center対応方法

docker-centerは、Dockerコンテナの登録、状態確認、操作を行うアプリケーションです。

この資料では、リポジトリ内のDocker関連ファイルをdocker-centerで利用できるようにするための実装方法を説明します。

## 起動スクリプト方式

リポジトリ内の起動スクリプトからDocker CLIを呼び出す方式です。単一コンテナには`scripts/launch.sh`を使います。複数のコンテナを個別に操作する場合は、サービスごとに`scripts/launch_<サービス名>.sh`を用意します。複数のコンテナをまとめて操作する場合は、同じスクリプトで扱う構成もあります。

```text
<リポジトリ>/
├── docker/
│   └── Dockerfile
└── scripts/
    └── launch.sh
```

複数のサービスを個別に扱い、それぞれにDockerfileを使う構成例です。

```text
<リポジトリ>/
├── docker/
│   ├── api/
│   │   └── Dockerfile
│   └── worker/
│       └── Dockerfile
└── scripts/
    ├── launch_api.sh
    └── launch_worker.sh
```

実行時には、プロジェクトルートをコンテナ内の`/workspace`へマウントします。これはDockerfileのビルドコンテキストとは別に指定します。

docker-centerは起動スクリプトに`CONTAINER_NAME_PREFIX`を環境変数として渡します。コンテナ名には`<CONTAINER_NAME_PREFIX><役割名>`を使い、`docker run --name`に指定します。

役割名は固定し、同じ接頭辞の中で重複させません。単一コンテナでは`service`、複数のサービスでは`api`や`worker`などを使います。個別に操作する場合は、サービスごとに起動スクリプトを分けます。

以下は単一コンテナ用の`scripts/launch.sh`の例です。

```bash
#!/usr/bin/env bash
set -e
: "${CONTAINER_NAME_PREFIX:?CONTAINER_NAME_PREFIXを設定してください}"
script_dir="$(realpath "$(dirname "$0")")" || exit 1
cd "$(dirname "$script_dir")" || exit 1
image_name="${IMAGE_NAME:-example-project-service}"
container_name="${CONTAINER_NAME_PREFIX}service"

if container_state="$(docker container inspect --format '{{.State.Status}}' "$container_name" 2>/dev/null)"; then
  if [ "$container_state" = "running" ]; then
    exit 0
  fi
  docker start "$container_name" >/dev/null
  exit 0
fi

docker build -t "$image_name" -f docker/Dockerfile docker
docker run -d --name "$container_name" \
  --user "$(id -u):$(id -g)" -v "$PWD:/workspace" -w /workspace \
  "$image_name" >/dev/null
```

同名のコンテナが稼働中なら、起動スクリプトは何もせず終了します。停止中なら`docker start`で再開し、コンテナがなければイメージをビルドして新規作成します。

停止スクリプトも同じコンテナ名を使います。コンテナが未作成または停止済みなら成功として終了し、稼働中なら停止します。Docker CLIやdaemonでエラーが起きた場合は、スクリプトを失敗させます。

停止済みコンテナを再利用するため、既存コンテナはイメージを再ビルドしても新しいイメージへ切り替わりません。Dockerfileの変更を反映する場合は、既存コンテナを削除して再作成する扱いを別途決めます。

`IMAGE_NAME`でイメージ名を指定します。例の`example-project-service`はプロジェクト名と役割名を組み合わせた仮の値です。実際の名前はプロジェクトごとに決め、既定値または`IMAGE_NAME`に設定します。

Dockerコマンドは実行ユーザーの権限で呼び出し、コンテナ内のプロセスも同じUIDとGIDで実行します。

### composeを使う起動・停止スクリプト方式

起動には`docker compose up`を使い、停止時には`docker compose down`でコンテナとネットワークを削除します。起動と停止は別々のスクリプトで実装します。

```text
<リポジトリ>/
├── docker/
│   ├── compose.yaml
│   ├── api/
│   │   └── Dockerfile
│   └── worker/
│       └── Dockerfile
└── scripts/
    ├── launch.sh
    └── down.sh
```

起動・停止スクリプトはリポジトリルートから実行できるようにします。操作方式`script`、起動コマンド`bash scripts/launch.sh`、停止コマンド`bash scripts/down.sh`、検出方式`container_name_prefix`を登録します。

起動と停止の両方で、同じ`CONTAINER_NAME_PREFIX`がスクリプトに渡されます。

`docker/compose.yaml`では、各サービスのコンテナ名に同じ接頭辞を付けます。

```yaml
services:
  api:
    container_name: ${CONTAINER_NAME_PREFIX}api
    build:
      context: ./api
      dockerfile: Dockerfile
    working_dir: /workspace
    volumes:
      - ../:/workspace
  worker:
    container_name: ${CONTAINER_NAME_PREFIX}worker
    build:
      context: ./worker
      dockerfile: Dockerfile
    working_dir: /workspace
    volumes:
      - ../:/workspace
```

起動スクリプトでは、接頭辞を`docker compose -p`のプロジェクト名にも使います。

```bash
#!/usr/bin/env bash
set -e
: "${CONTAINER_NAME_PREFIX:?CONTAINER_NAME_PREFIXを設定してください}"
script_dir="$(realpath "$(dirname "$0")")" || exit 1
cd "$(dirname "$script_dir")" || exit 1
docker compose -p "$CONTAINER_NAME_PREFIX" -f docker/compose.yaml up --build --detach --remove-orphans
```

停止スクリプトでは、起動時と同じプロジェクト名とcomposeファイルを指定します。`docker compose down`でコンテナとネットワークを削除し、名前付きボリュームは保持します。

```bash
#!/usr/bin/env bash
set -e
: "${CONTAINER_NAME_PREFIX:?CONTAINER_NAME_PREFIXを設定してください}"
script_dir="$(realpath "$(dirname "$0")")" || exit 1
cd "$(dirname "$script_dir")" || exit 1
docker compose -p "$CONTAINER_NAME_PREFIX" -f docker/compose.yaml down --remove-orphans
```

`CONTAINER_NAME_PREFIX`には、同じDockerホスト上で重複せず、`docker compose -p`に指定できる値を設定します。

## docker compose方式

```text
<リポジトリ>/
└── docker/
    ├── compose.yaml
    ├── api/
    │   └── Dockerfile
    └── worker/
        └── Dockerfile
```

`docker/compose.yaml`の例です。

```yaml
name: example-project

services:
  api:
    image: ${API_IMAGE_NAME:-example-project-api}
    build:
      context: ./api
      dockerfile: Dockerfile
    working_dir: /workspace
    volumes:
      - ../:/workspace
  worker:
    image: ${WORKER_IMAGE_NAME:-example-project-worker}
    build:
      context: ./worker
      dockerfile: Dockerfile
    working_dir: /workspace
    volumes:
      - ../:/workspace
```

`name`にはDockerホスト上で一意になるプロジェクト名を設定します。これはdocker-centerのEntry表示名とは別です。

サービス名はコンテナの役割に合わせます。イメージ名の既定値にはプロジェクト名とサービス名を含めます。必要に応じて`API_IMAGE_NAME`、`WORKER_IMAGE_NAME`で上書きします。

各`build.context`には、そのサービスのDockerfileとビルドに必要なファイルだけを含むディレクトリを指定します。

## 共通の実装上の注意

`launch.sh`、`down.sh`などのスクリプトは、特別な指示がない限り追加依存を最小限にします。Pythonやjqなどの実行環境・ツールを前提にせず、シェルとDocker CLIを中心に実装します。

## 実装のヒント

### Dockerfileとビルドコンテキスト

同一リポジトリで使うDockerfileが1つなら、`docker/Dockerfile`に置き、`docker/`をビルドコンテキストにします。複数のDockerfileをサービスごとに使う場合は、`docker/<サービス名>/Dockerfile`に分け、それぞれのサービス用ディレクトリをビルドコンテキストにします。コンテナや起動スクリプトが複数あっても、Dockerfileをサービスごとに分けるとは限りません。

`.dockerignore`で不要ファイルを除外する構成はアンチパターンです。各ビルドコンテキストには、Dockerfileとイメージ作成に必要なファイルだけを置きます。リポジトリルート全体をコンテキストにせず、`.env`、認証情報、秘密鍵などをコンテキストに含めないでください。

アプリケーションソースはDockerfileの`COPY`でイメージに含めず、実行時にプロジェクトルートを`/workspace`へマウントします。

### Pythonの依存環境を起動時に作る場合

ここではPythonを例に説明します。
Python本体と依存管理ツールはイメージに含め、アプリケーションのパッケージはイメージ作成時にインストールしません。コンテナ起動時に、ロックファイルなど固定された情報から専用環境へ同期します。

uvに限らず、アプリケーションのパッケージ依存を固定情報から専用環境へ同期し、その環境と取得キャッシュの保存先を指定できるツールには、同じ運用を適用します。対象はアプリケーションのパッケージ依存です。OSパッケージやDockerビルドキャッシュは含めません。

#### uvの設定例

uvを使う場合は、DockerイメージにPythonと`uv`コマンドを用意します。

管理対象ごとに、ホスト側の`_cache/<ツール名>_uv_cache`をuvのキャッシュに、`_cache/<ツール名>_uv_venv`を仮想環境に使います。プロジェクトルートをコンテナ内の`/workspace`へマウントすると、これらは`/workspace/_cache/<ツール名>_uv_cache`と`/workspace/_cache/<ツール名>_uv_venv`になります。

コンテナ内では、これらのパスをそれぞれ`UV_CACHE_DIR`と`UV_PROJECT_ENVIRONMENT`に設定します。実行ユーザーが書き込めるようにしてください。どちらも実行時の保存先であり、Dockerビルドキャッシュとは別です。

uv同期とアプリケーション起動の処理は、リポジトリ内の`scripts/container-start.sh`に置きます。これはホスト側の起動スクリプト`scripts/launch.sh`とは別のファイルです。

例の`target_name`と`example_project`は各プロジェクトに合わせます。

```sh
#!/bin/sh
set -eu
target_name="example-project-service"
export UV_CACHE_DIR="/workspace/_cache/${target_name}_uv_cache"
export UV_PROJECT_ENVIRONMENT="/workspace/_cache/${target_name}_uv_venv"
uv sync --locked
exec uv run --no-sync python -m example_project
```

以下は単一Dockerfileを使う場合の一例です。起動内容がサービスごとに異なる場合は、スクリプトを分け、各サービスの`command`から対応するファイルを呼び出します。

```text
<リポジトリ>/
├── compose.yaml
├── docker/
│   └── Dockerfile
└── scripts/
    └── container-start.sh
```

`compose.yaml`:

```yaml
services:
  app:
    build:
      context: ./docker
      dockerfile: Dockerfile
    working_dir: /workspace
    volumes:
      - .:/workspace
    command: ["/bin/sh", "/workspace/scripts/container-start.sh"]
```

composeの`command`にはスクリプトを配列で指定します。シェル処理は`command`に直接書かず、スクリプトに置きます。

リポジトリルートでDocker CLIから起動する場合の例です。

```sh
docker run --rm \
  --volume "$PWD:/workspace" \
  --workdir /workspace \
  --entrypoint /bin/sh \
  example-project-service \
  /workspace/scripts/container-start.sh
```

複数サービスでは、各サービスの起動スクリプトを指定します。

### dev_mcp（開発用MCP）の例

開発用MCPサーバーは、MCPごとに`dev_mcp/<mcp名>/`へ配置します。この例では、MCP名を`example_mcp`とします。

```text
<リポジトリ>/
├── dev_mcp/
│   └── example_mcp/
│       ├── compose.yml
│       ├── .env.example
│       ├── prepare.sh
│       ├── setup.sh
│       ├── .python-version
│       ├── pyproject.toml
│       ├── uv.lock
│       ├── server.py
│       └── docker/
│           └── Dockerfile
└── _cache/
    ├── example_mcp_uv_cache/
    ├── example_mcp_uv_venv/
    └── example_mcp_uv_python/
```

`dev_mcp/example_mcp/compose.yml`:

```yaml
services:
  example_mcp:
    build:
      context: ./docker
      dockerfile: Dockerfile
    working_dir: /workspace/dev_mcp/example_mcp
    user: "${UID:-1000}:${GID:-1000}"
    environment:
      EXAMPLE_MCP_PORT: "${EXAMPLE_MCP_PORT:?EXAMPLE_MCP_PORTを設定してください}"
      UV_CACHE_DIR: /workspace/_cache/example_mcp_uv_cache
      UV_PROJECT_ENVIRONMENT: /workspace/_cache/example_mcp_uv_venv
      UV_PYTHON_INSTALL_DIR: /workspace/_cache/example_mcp_uv_python
    ports:
      - "127.0.0.1:${EXAMPLE_MCP_PORT:?EXAMPLE_MCP_PORTを設定してください}:${EXAMPLE_MCP_PORT:?EXAMPLE_MCP_PORTを設定してください}"
    volumes:
      - ../..:/workspace:ro
      - ../../_cache/example_mcp_uv_cache:/workspace/_cache/example_mcp_uv_cache
      - ../../_cache/example_mcp_uv_venv:/workspace/_cache/example_mcp_uv_venv
      - ../../_cache/example_mcp_uv_python:/workspace/_cache/example_mcp_uv_python
    command: ["/bin/sh", "/workspace/dev_mcp/example_mcp/setup.sh"]
```

リポジトリルートを`/workspace`にマウントし、作業ディレクトリにはその中の`dev_mcp/example_mcp`を指定します。

`docker/Dockerfile`:

```dockerfile
FROM ubuntu:26.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
    && rm -rf /var/lib/apt/lists/*
```

`prepare.sh`はリポジトリルートから起動前に実行し、uvキャッシュ、仮想環境、uv管理Pythonの保存先をホスト側に作ります。

`dev_mcp/example_mcp/prepare.sh`:

```sh
#!/bin/sh
set -eu

mkdir -p _cache/example_mcp_uv_cache _cache/example_mcp_uv_venv _cache/example_mcp_uv_python
```

コンテナ起動時に`setup.sh`を実行し、`.python-version`のPythonを`UV_PYTHON_INSTALL_DIR`に用意してから、`uv sync`で依存関係を同期し、MCPサーバーを起動します。Python本体と依存関係はDockerイメージに含めません。Pythonの保存先はマウントしているため、導入済みの版を再利用でき、`.python-version`の変更は次回起動時に反映されます。

`dev_mcp/example_mcp/setup.sh`:

```sh
#!/bin/sh
set -eu

uv python install --no-bin
uv sync --locked
exec uv run --no-sync python server.py
```

`dev_mcp/example_mcp/.python-version`には、このMCPで使うPythonの版を指定します。

```text
3.15
```

`pyproject.toml`にはFastMCPなどサーバーの依存関係を記述し、対応する`uv.lock`を用意します。

```toml
[project]
name = "example-mcp"
version = "0.1.0"
requires-python = ">=3.15,<3.16"
dependencies = ["fastmcp"]

[tool.uv]
package = false
```

`server.py`ではFastMCPサーバーを起動し、`EXAMPLE_MCP_PORT`で指定されたポートをコンテナ内の全インターフェースで待ち受けます。

```python
import os

from fastmcp import FastMCP

mcp = FastMCP("example_mcp")

if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ["EXAMPLE_MCP_PORT"]),
    )
```

`dev_mcp/example_mcp/.env.example`:

```dotenv
EXAMPLE_MCP_PORT=<このMCPで使用するポート番号>
```

`EXAMPLE_MCP_PORT`は変数名の例です。実際のMCP名に合わせて置き換えてください。

