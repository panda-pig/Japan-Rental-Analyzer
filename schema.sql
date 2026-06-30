-- 房源主表
CREATE TABLE IF NOT EXISTS rental_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT,
    source_url TEXT,
    detail_url TEXT UNIQUE,
    title TEXT,
    address TEXT,
    prefecture TEXT,
    city TEXT,
    ward TEXT,
    nearest_station TEXT,
    line_name TEXT,
    walk_minutes INTEGER,
    rent INTEGER,
    management_fee INTEGER,
    total_monthly_cost INTEGER,
    deposit INTEGER,
    key_money INTEGER,
    initial_cost_estimate INTEGER,
    layout TEXT,
    area_m2 REAL,
    price_per_m2 REAL,
    floor INTEGER,
    total_floors INTEGER,
    building_age INTEGER,
    structure TEXT,
    pet_allowed INTEGER DEFAULT 0,
    two_person_allowed INTEGER DEFAULT 0,
    bath_toilet_separate INTEGER DEFAULT 0,
    auto_lock INTEGER DEFAULT 0,
    delivery_box INTEGER DEFAULT 0,
    south_facing INTEGER DEFAULT 0,
    aircon INTEGER DEFAULT 0,
    image_url TEXT,
    listing_hash TEXT,
    duplicate_group_id TEXT,
    is_active INTEGER DEFAULT 1,
    commute_minutes INTEGER,
    commute_target_station TEXT,
    first_seen_at TEXT,
    last_seen_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 评分表
CREATE TABLE IF NOT EXISTS listing_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    budget_score INTEGER DEFAULT 0,
    area_score INTEGER DEFAULT 0,
    commute_score INTEGER DEFAULT 0,
    floor_score INTEGER DEFAULT 0,
    pet_score INTEGER DEFAULT 0,
    station_score INTEGER DEFAULT 0,
    age_score INTEGER DEFAULT 0,
    initial_cost_score INTEGER DEFAULT 0,
    feature_score INTEGER DEFAULT 0,
    total_score INTEGER DEFAULT 0,
    score_reason TEXT,
    commute_minutes INTEGER,
    commute_resolved INTEGER DEFAULT 0,
    calculated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (listing_id) REFERENCES rental_listings(id)
);

-- 收藏/进度状态表
CREATE TABLE IF NOT EXISTS listing_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    status TEXT,
    priority INTEGER,
    memo TEXT,
    contacted INTEGER DEFAULT 0,
    viewing_date TEXT,
    decision TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (listing_id) REFERENCES rental_listings(id)
);

-- 价格历史表
CREATE TABLE IF NOT EXISTS listing_price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    rent INTEGER,
    management_fee INTEGER,
    total_monthly_cost INTEGER,
    checked_at TEXT,
    FOREIGN KEY (listing_id) REFERENCES rental_listings(id)
);

-- 数据源配置表
CREATE TABLE IF NOT EXISTS source_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    platform TEXT NOT NULL,
    source_url TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    max_pages INTEGER DEFAULT 2,
    last_scraped_at TEXT,
    last_status TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 导入/抓取日志表
CREATE TABLE IF NOT EXISTS import_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_type TEXT,
    source_name TEXT,
    total_rows INTEGER,
    inserted_count INTEGER,
    updated_count INTEGER,
    duplicate_count INTEGER,
    error_count INTEGER,
    message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 用户偏好设置表(单行)
CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    max_total_monthly_cost INTEGER DEFAULT 140000,
    min_area_m2 REAL DEFAULT 35,
    ideal_area_m2 REAL DEFAULT 40,
    min_floor INTEGER DEFAULT 2,
    require_pet_allowed INTEGER DEFAULT 0,
    max_walk_minutes INTEGER DEFAULT 15,
    ideal_walk_minutes INTEGER DEFAULT 10,
    max_building_age INTEGER DEFAULT 20,
    target_station TEXT,
    budget_weight INTEGER DEFAULT 20,
    area_weight INTEGER DEFAULT 15,
    commute_weight INTEGER DEFAULT 15,
    floor_weight INTEGER DEFAULT 10,
    pet_weight INTEGER DEFAULT 15,
    station_weight INTEGER DEFAULT 10,
    age_weight INTEGER DEFAULT 10,
    initial_cost_weight INTEGER DEFAULT 5,
    broker_fee_rate REAL DEFAULT 0.55,
    prepaid_rent_months INTEGER DEFAULT 1,
    misc_cost INTEGER DEFAULT 40000,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_listings_hash ON rental_listings(listing_hash);
CREATE INDEX IF NOT EXISTS idx_listings_platform ON rental_listings(platform);
CREATE INDEX IF NOT EXISTS idx_listings_ward ON rental_listings(ward);
CREATE INDEX IF NOT EXISTS idx_scores_total ON listing_scores(total_score);