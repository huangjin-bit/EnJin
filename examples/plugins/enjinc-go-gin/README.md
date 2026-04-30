# enjinc-go-gin

Go Gin Web Framework target for EnJin Compiler.

Generates a complete Go project with Gin framework from `.ej` intent source files.

## Output Structure

```
go_gin/
├── main.go                    # Application entry point
├── go.mod                     # Go module definition
├── config/config.go           # Configuration loading
├── router/router.go           # Route registration
├── model/<struct>.go          # Data models
├── service/<fn>.go            # Business logic
└── handler/<route>.go         # HTTP handlers
```

## Install

```bash
pip install enjinc-go-gin
```

## Usage

```bash
enjinc build app.ej --target go_gin
```

## Development

```bash
pip install -e .
enjinc targets  # verify go_gin appears
enjinc build examples/user_management.ej --target go_gin --out output
```

## Test

```bash
pytest tests/
```
