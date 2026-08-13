import { NextResponse } from 'next/server';
import { execFile } from 'child_process';
import path from 'path';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

export async function GET() {
  try {
    const backendDir = path.resolve(process.cwd(), '..', 'backend');
    const pythonExecutable =
      process.platform === 'win32'
        ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
        : path.join(backendDir, '.venv', 'bin', 'python');
    const dbPath = path.join(backendDir, 'call_analytics.db');

    const script = `
import json, sqlite3
conn = sqlite3.connect(r'${dbPath.replace(/\\/g, '\\\\')}')
conn.row_factory = sqlite3.Row
try:
    row = conn.execute("SELECT COUNT(*) AS total, SUM(CASE WHEN successful = 1 THEN 1 ELSE 0 END) AS successful, SUM(CASE WHEN successful = 0 THEN 1 ELSE 0 END) AS failed, SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active FROM calls").fetchone()
    total = int(row['total'] or 0)
    successful = int(row['successful'] or 0)
    failed = int(row['failed'] or 0)
    active = int(row['active'] or 0)
    success_rate = round((successful / total) * 100, 2) if total > 0 else 0
    print(json.dumps({"total": total, "successful": successful, "failed": failed, "active": active, "success_rate": success_rate}))
finally:
    conn.close()
`;

    const { stdout } = await execFileAsync(pythonExecutable, ['-c', script], {
      cwd: backendDir,
      maxBuffer: 1024 * 1024,
    });

    const data = JSON.parse(stdout.toString().trim() || '{}');

    return NextResponse.json(
      {
        total: Number(data.total ?? 0),
        successful: Number(data.successful ?? 0),
        failed: Number(data.failed ?? 0),
        active: Number(data.active ?? 0),
        success_rate: Number(data.success_rate ?? 0),
      },
      {
        headers: {
          'Cache-Control': 'no-store',
        },
      }
    );
  } catch (error) {
    console.error('Analytics API error:', error);

    return NextResponse.json(
      {
        total: 0,
        successful: 0,
        failed: 0,
        active: 0,
        success_rate: 0,
      },
      {
        status: 500,
        headers: {
          'Cache-Control': 'no-store',
        },
      }
    );
  }
}