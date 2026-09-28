import pandas as pd

df = pd.read_csv('OP sin asignar.csv', encoding='latin1', sep=';')
print(f"Total filas: {len(df)}")
df_op = df[df['OP'].notnull() & (df['OP'].astype(str).str.strip() != '')]
print(f"Filas con OP completada: {len(df_op)}")

for idx, row in df_op.iterrows():
    print(f"Fila {row['#']}: Decreto={row['Decreto']}, Cuota={row['Cuota']}, Fecha={row['Fecha Pago']}, Monto={row['Importe Pagado']}, OP='{row['OP']}', Destino='{row['Obra Destino']}', Obs='{row['Observaciones']}'")
