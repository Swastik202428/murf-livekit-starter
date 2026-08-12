import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from .escalation import (
    init_escalation_db,
    get_open_escalations,
)


# ============================================================
# DATABASE
# ============================================================

DB_CONN = init_escalation_db()


# ============================================================
# CONFIG
# ============================================================

HOST = "127.0.0.1"
PORT = 8001


# ============================================================
# API HANDLER
# ============================================================

class EscalationHandler(BaseHTTPRequestHandler):

    def _send_json(
        self,
        data,
        status_code=200,
    ):
        response = json.dumps(
            data,
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(status_code)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "http://localhost:3000",
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, OPTIONS",
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )

        self.end_headers()

        self.wfile.write(response)

    def do_OPTIONS(self):

        self.send_response(204)

        self.send_header(
            "Access-Control-Allow-Origin",
            "http://localhost:3000",
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, OPTIONS",
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )

        self.end_headers()

    def do_GET(self):

        if self.path == "/api/escalations":

            try:

                requests = get_open_escalations(
                    DB_CONN
                )

                self._send_json(
                    {
                        "success": True,
                        "requests": requests,
                    }
                )

            except Exception as exc:

                self._send_json(
                    {
                        "success": False,
                        "error": str(exc),
                    },
                    500,
                )

            return

        self._send_json(
            {
                "success": False,
                "error": "Not found",
            },
            404,
        )

    def log_message(
        self,
        format,
        *args,
    ):
        print(
            "[Escalation API]",
            format % args,
        )


# ============================================================
# SERVER
# ============================================================

def main():

    server = HTTPServer(
        (HOST, PORT),
        EscalationHandler,
    )

    print(
        f"Human Help API running at "
        f"http://{HOST}:{PORT}"
    )

    print(
        "Endpoint:"
    )

    print(
        f"http://{HOST}:{PORT}/api/escalations"
    )

    try:
        server.serve_forever()

    except KeyboardInterrupt:

        print(
            "\nHuman Help API stopped."
        )

    finally:

        server.server_close()


if __name__ == "__main__":
    main()