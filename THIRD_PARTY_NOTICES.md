# Third-party notices

## MCP reference servers (Git, SQLite)

`data/servers/upstream/git_2025.1.14/` and `data/servers/upstream/sqlite_9120679/` are copies of the Git and SQLite servers from the Model Context Protocol reference servers (https://github.com/modelcontextprotocol/servers and https://github.com/modelcontextprotocol/servers-archived). Both are distributed under the MIT License. The Git copy includes its own `LICENSE` file. The SQLite server is distributed under the license of the servers-archived repository:

```
MIT License

Copyright (c) 2024 Anthropic, PBC

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Desktop Commander

`data/servers/commander_0.1.39/` contains only the build and test files written for this study. The Docker image installs `@wonderwhy-er/desktop-commander` 0.1.39 from npm, which is distributed under the MIT License (Copyright (c) 2024-2025 Eduard Ruzga and Desktop Commander Contributors).

## MCPTox

This study uses the MCPTox benchmark (Z. Wang et al., "MCPTox: A Benchmark for Tool Poisoning on Real-World MCP Servers," AAAI 2026; https://github.com/zhiqiangwang4/MCPTox-Benchmark). The MCPTox case table is not redistributed here. Run outputs and analysis files quote short parts of MCPTox tool descriptions and user requests where needed to report results.
