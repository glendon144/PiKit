-- This script will help you debug and fix the missing `id` column in the documents table
-- Please review your schema creation logic or run the following fix manually if needed

-- Check the structure of your current documents table
PRAGMA table_info(documents);

-- If the `id` column is missing, recreate the table properly (backup data first)

-- Step 1: Rename old table
ALTER TABLE documents RENAME TO documents_old;

-- Step 2: Create new table with correct schema
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);

-- Step 3: Copy data back
INSERT INTO documents (title, body)
SELECT title, body FROM documents_old;

-- Step 4: Drop old table
DROP TABLE documents_old;

-- Now the documents table should include an `id` column and be compatible with your app
