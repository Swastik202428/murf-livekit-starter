from http.server import (
    BaseHTTPRequestHandler,
    HTTPServer,
)
import json

from call_analytics import init_analytics_db, get_stats


class AnalyticsHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        if self.path in {"/analytics", "/api/analytics"}:

            conn = init_analytics_db()
            stats = get_stats(conn)

            response = json.dumps(
                stats
            ).encode("utf-8")

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "application/json",
            )

            self.send_header(
                "Access-Control-Allow-Origin",
                "*",
            )

            self.end_headers()

            self.wfile.write(
                response
            )

            return

        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":

    server = HTTPServer(
        ("0.0.0.0", 8000),
        AnalyticsHandler,
    )

    print(
        "Analytics API running at "
        "http://localhost:8000/api/analytics"
    )

    server.serve_forever()