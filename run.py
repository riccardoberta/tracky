from __future__ import annotations

from tracky import create_app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
