# Sources and build provenance

Official kit downloaded on 2026-11-21 from:

- [mechfight-kit.tar.gz](https://www.joinbuilders.org/buildathon/tracks/builders/files/mechfight-kit.tar.gz)
- [protocol.md](https://www.joinbuilders.org/buildathon/tracks/builders/files/protocol.md)
- [competition page](https://www.joinbuilders.org/buildathon/tracks/builders)

`arena/`, `check/`, `docs/protocol.md`, and `mechfight.schema.json` are copied from
the kit. `mechfight.py` is the kit's Python wrapper with one change: constructor
failure exits with status 1 instead of sending `ready` for an uninitialized bot.
That ensures a missing map is caught before scored play.

`sentinel/`, `bot.py`, behavioral tests, tools, workflow, and project documentation
were written for this project. No game website bundle is included in the project.

The Docker base is the official `library/python` image, version
`3.13.9-slim-bookworm`, pinned to its Docker Hub manifest digest:

```text
sha256:b685a4fa58bb19d1814d78a1ec0f0208f351452724f78b20212c984d6e124a34
```

The manifest was fetched from Docker Hub during preparation and includes a
`linux/amd64` image. GitHub's checkout action is pinned to its v4.2.2 commit.
No package manager installs or unpinned application dependencies are used.
