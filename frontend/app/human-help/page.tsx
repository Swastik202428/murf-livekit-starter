"use client";

import { useEffect, useState } from "react";

type Escalation = {
  reference_id: string;
  caller_id: string;
  caller_name: string;
  issue_type: string;
  summary: string;
  agent_checked: string;
  urgency: string;
  language: string;
  preferred_follow_up: string;
  status: string;
  created_at: string;
};

export default function HumanHelpPage() {
  const [requests, setRequests] = useState<Escalation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadRequests() {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(
        "http://127.0.0.1:8001/api/escalations",
        {
          cache: "no-store",
        }
      );

      if (!response.ok) {
        throw new Error("Unable to load requests");
      }

      const data = await response.json();

      if (!data.success) {
        throw new Error(
          data.error || "Unable to load requests"
        );
      }

      setRequests(data.requests || []);
    } catch (err) {
      console.error(err);
      setError(
        "Human Help API se requests load nahi ho pa rahi hain."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRequests();

    const interval = setInterval(
      loadRequests,
      5000
    );

    return () => clearInterval(interval);
  }, []);

  return (
    <main
      style={{
        minHeight: "100vh",
        padding: "40px",
        background: "#f5f7fb",
        color: "#111827",
      }}
    >
      <div
        style={{
          maxWidth: "1100px",
          margin: "0 auto",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "30px",
          }}
        >
          <div>
            <h1
              style={{
                fontSize: "32px",
                fontWeight: 700,
                marginBottom: "8px",
              }}
            >
              Human Help Requests
            </h1>

            <p
              style={{
                color: "#6b7280",
              }}
            >
              HealthAccess escalation dashboard
            </p>
          </div>

          <button
            onClick={loadRequests}
            style={{
              padding: "10px 18px",
              borderRadius: "8px",
              border: "1px solid #d1d5db",
              background: "white",
              cursor: "pointer",
              fontWeight: 600,
            }}
          >
            Refresh
          </button>
        </div>

        {loading && (
          <div
            style={{
              background: "white",
              padding: "30px",
              borderRadius: "12px",
            }}
          >
            Loading human-help requests...
          </div>
        )}

        {error && (
          <div
            style={{
              background: "#fee2e2",
              border: "1px solid #fecaca",
              color: "#991b1b",
              padding: "18px",
              borderRadius: "10px",
              marginBottom: "20px",
            }}
          >
            {error}
          </div>
        )}

        {!loading &&
          !error &&
          requests.length === 0 && (
            <div
              style={{
                background: "white",
                padding: "50px",
                borderRadius: "12px",
                textAlign: "center",
              }}
            >
              <h2
                style={{
                  fontSize: "22px",
                  marginBottom: "10px",
                }}
              >
                No open requests
              </h2>

              <p
                style={{
                  color: "#6b7280",
                }}
              >
                Human-help requests created by HealthAccess
                will appear here.
              </p>
            </div>
          )}

        <div
          style={{
            display: "grid",
            gap: "20px",
          }}
        >
          {requests.map((request) => (
            <div
              key={request.reference_id}
              style={{
                background: "white",
                borderRadius: "14px",
                padding: "24px",
                border: "1px solid #e5e7eb",
                boxShadow:
                  "0 4px 12px rgba(0,0,0,0.05)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  gap: "20px",
                  marginBottom: "20px",
                }}
              >
                <div>
                  <div
                    style={{
                      fontSize: "13px",
                      color: "#6b7280",
                      marginBottom: "5px",
                    }}
                  >
                    Reference ID
                  </div>

                  <div
                    style={{
                      fontSize: "20px",
                      fontWeight: 700,
                    }}
                  >
                    {request.reference_id}
                  </div>
                </div>

                <div
                  style={{
                    display: "flex",
                    gap: "8px",
                  }}
                >
                  <span
                    style={{
                      padding: "6px 10px",
                      borderRadius: "999px",
                      background:
                        request.urgency === "emergency"
                          ? "#fee2e2"
                          : "#fef3c7",
                      color:
                        request.urgency === "emergency"
                          ? "#991b1b"
                          : "#92400e",
                      fontSize: "12px",
                      fontWeight: 700,
                      textTransform: "uppercase",
                    }}
                  >
                    {request.urgency}
                  </span>

                  <span
                    style={{
                      padding: "6px 10px",
                      borderRadius: "999px",
                      background: "#dcfce7",
                      color: "#166534",
                      fontSize: "12px",
                      fontWeight: 700,
                      textTransform: "uppercase",
                    }}
                  >
                    {request.status}
                  </span>
                </div>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "repeat(auto-fit, minmax(220px, 1fr))",
                  gap: "18px",
                  marginBottom: "20px",
                }}
              >
                <Info
                  label="Caller"
                  value={
                    request.caller_name ||
                    "Caller"
                  }
                />

                <Info
                  label="Issue"
                  value={request.issue_type}
                />

                <Info
                  label="Language"
                  value={
                    request.language ||
                    "Not specified"
                  }
                />

                <Info
                  label="Follow-up"
                  value={
                    request.preferred_follow_up ||
                    "Not specified"
                  }
                />
              </div>

              <section
                style={{
                  marginBottom: "18px",
                }}
              >
                <h3
                  style={{
                    fontSize: "14px",
                    fontWeight: 700,
                    marginBottom: "8px",
                  }}
                >
                  What happened
                </h3>

                <p
                  style={{
                    lineHeight: 1.6,
                    color: "#374151",
                  }}
                >
                  {request.summary}
                </p>
              </section>

              <section
                style={{
                  marginBottom: "18px",
                }}
              >
                <h3
                  style={{
                    fontSize: "14px",
                    fontWeight: 700,
                    marginBottom: "8px",
                  }}
                >
                  What the agent checked
                </h3>

                <p
                  style={{
                    lineHeight: 1.6,
                    color: "#374151",
                  }}
                >
                  {request.agent_checked}
                </p>
              </section>

              <div
                style={{
                  borderTop:
                    "1px solid #e5e7eb",
                  paddingTop: "14px",
                  fontSize: "12px",
                  color: "#6b7280",
                }}
              >
                Created:{" "}
                {new Date(
                  request.created_at
                ).toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}

function Info({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div>
      <div
        style={{
          fontSize: "12px",
          color: "#6b7280",
          marginBottom: "5px",
        }}
      >
        {label}
      </div>

      <div
        style={{
          fontWeight: 600,
        }}
      >
        {value}
      </div>
    </div>
  );
}