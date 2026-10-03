"""One-time manual migration: copy every table from schema 'main' into a
new schema 'app', which the bot's own role (DB_USER) ends up owning
outright -- whoever creates a table owns it in Postgres, regardless of who
owns the source it was copied from. This exists because ownership of
tables in 'main' ended up split across multiple roles (bradbotrole,
BradBotUser, others) with no available connection -- including the Aurora
DSQL admin-scope IAM token -- able to reassign that ownership after the
fact. Run manually once, NOT part of scripts/migrate.py's normal flow:

    python scripts/migrate_schema_data.py

Requires AWS_REGION, DB_HOST, DB_NAME, DB_USER in the environment (same as
the bot itself). The rest of the codebase already points at 'app.*' --
this script is what actually gets the data there.
"""
import boto3, os, psycopg2, traceback

region = os.environ['AWS_REGION']
host = os.environ['DB_HOST']
dbname = os.environ.get('DB_NAME', 'postgres')
bot_user = os.environ.get('DB_USER', 'BradBotUser')

def connect_as(user, admin=False):
    client = boto3.client('dsql', region_name=region)
    if admin:
        token = client.generate_db_connect_admin_auth_token(host, region)
    else:
        token = client.generate_db_connect_auth_token(host, region)
    conn = psycopg2.connect(host=host, port=5432, dbname=dbname, user=user, password=token, sslmode='require')
    conn.autocommit = True
    return conn

# Step 1: create the new schema, preferring the bot's own regular connection
# (if it already owns whatever it creates) and only falling back to the
# admin token + a plain GRANT (not an ownership transfer -- that's exactly
# what's been failing) if the bot can't create schemas itself.
try:
    bot_conn = connect_as(bot_user, admin=False)
    bot_cur = bot_conn.cursor()
    bot_cur.execute("CREATE SCHEMA IF NOT EXISTS app")
    print(f"Created schema 'app' directly as {bot_user!r}")
except Exception as e:
    print(f"Could not create schema as {bot_user!r} ({e}); falling back to admin token")
    admin_conn = connect_as('admin', admin=True)
    admin_cur = admin_conn.cursor()
    admin_cur.execute("CREATE SCHEMA IF NOT EXISTS app")
    admin_cur.execute(f'GRANT ALL ON SCHEMA app TO "{bot_user}"')
    print(f"Created schema 'app' as admin and granted {bot_user!r} full rights on it")
    bot_conn = connect_as(bot_user, admin=False)
    bot_cur = bot_conn.cursor()

# Step 2: copy every table's structure + data into the new schema, as the
# bot's own role -- whoever creates a table owns it, so this sidesteps
# needing any ALTER ... OWNER TO at all.
bot_cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'")
tables = [r[0] for r in bot_cur.fetchall()]
print(f"\nCopying {len(tables)} tables from main -> app...\n")

for t in tables:
    try:
        bot_cur.execute(f'CREATE TABLE IF NOT EXISTS app."{t}" (LIKE main."{t}" INCLUDING ALL)')
        bot_cur.execute(f'INSERT INTO app."{t}" SELECT * FROM main."{t}"')
        bot_cur.execute(f'SELECT count(*) FROM app."{t}"')
        count = bot_cur.fetchone()[0]
        print(f"  {t}: copied, {count} row(s)")
    except Exception as e:
        print(f"  {t}: FAILED -> {type(e).__name__}: {e}")
        traceback.print_exc()

print("\nDone. Verify row counts above look right before redeploying.")
