import sqlite3
conn = sqlite3.connect('decretometro.db')
conn.row_factory = sqlite3.Row
print(dict(conn.execute("SELECT * FROM op_bejerman WHERE nro_op = '3791'").fetchone() or {}))
print("Done")
