# Check if sqlite3 is installed
which sqlite3

# If it is installed, this will show you the path to the binary (e.g., /usr/bin/sqlite3)

# To open your application's SQLite database:
sqlite3 path/to/your/database.db

# Example if your database file is called documents.db and located in your current directory:
sqlite3 documents.db

# Inside the shell, you can run commands like:
.tables          -- list all tables
.schema          -- show the schema of the database
SELECT * FROM documents; -- view table contents

# To exit the SQLite shell:
.quit
