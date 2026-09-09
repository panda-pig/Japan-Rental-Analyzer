"""Local, versioned schema upgrades; external APIs are never needed here."""
import json

VERSION = 1


def migrate(conn):
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (VERSION,)).fetchone():
            conn.commit()
            return
        columns = {r[1] for r in conn.execute("PRAGMA table_info(region_stats)")}
        additions = {
            "trade_price_per_m2": "INTEGER", "trade_count": "INTEGER",
            "flood_rank": "INTEGER", "sediment_count": "INTEGER", "hazard_level": "TEXT",
            "rent_layout": "TEXT", "rent_source": "TEXT NOT NULL DEFAULT 'unverified'",
            "rent_fetched_at": "TEXT", "stats_method": "TEXT NOT NULL DEFAULT 'unverified'",
        }
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE region_stats ADD COLUMN {name} {definition}")
        history_cols = {r[1] for r in conn.execute("PRAGMA table_info(listing_price_history)")}
        if "observation_kind" not in history_cols:
            # Old rows stored the previous price at the refresh time. Preserve them,
            # but don't present their timestamps as actual observations.
            conn.execute("ALTER TABLE listing_price_history ADD COLUMN observation_kind "
                         "TEXT NOT NULL DEFAULT 'legacy'")
        for table, timestamp in (("listing_status", "updated_at"), ("listing_scores", "calculated_at")):
            duplicates = conn.execute(
                f"SELECT listing_id FROM {table} GROUP BY listing_id HAVING COUNT(*) > 1").fetchall()
            for (lid,) in duplicates:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE listing_id=? ORDER BY {timestamp} DESC, id DESC",
                    (lid,)).fetchall()
                # Archive every original row before merging; notes remain recoverable.
                for row in rows:
                    conn.execute("INSERT INTO migration_archive(table_name,row_data) VALUES (?,?)",
                                 (table, json.dumps(dict(row), ensure_ascii=False)))
                if table == "listing_status":
                    merged = dict(rows[0])
                    for key in ("status", "priority", "viewing_date", "decision"):
                        merged[key] = next((r[key] for r in rows if r[key] is not None), None)
                    notes = list(dict.fromkeys(r["memo"] for r in rows if r["memo"]))
                    conn.execute("UPDATE listing_status SET status=?, priority=?, viewing_date=?, "
                                 "decision=?, memo=?, contacted=? WHERE id=?",
                                 (merged["status"], merged["priority"], merged["viewing_date"],
                                  merged["decision"], "\n\n".join(notes) or None,
                                  max(r["contacted"] or 0 for r in rows), merged["id"]))
                conn.execute(f"DELETE FROM {table} WHERE listing_id=? AND id<>?", (lid, rows[0]["id"]))
            conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_listing ON {table}(listing_id)")
        conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (VERSION,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
