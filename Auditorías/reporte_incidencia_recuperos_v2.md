# 📋 Reporte Técnico de Incidencia y Guía Preventiva para Versión 2.0

### 1. Resumen Ejecutivo
* **Módulo Afectado:** Cobros y Distribución (`components/tab_estado.py` / Vista de Tarjetas de Cobranzas).
* **Severidad:** Media-Alta (Bloqueo funcional de operaciones de recupero en la interfaz de usuario).
* **Naturaleza del Fallo:** Fuga de ámbito de variables (*Variable Scope Leak*) entre el bucle de cálculo/agregación y el bucle de renderizado paginado en Streamlit.

---

### 2. Síntoma e Impacto en el Usuario
Al inspeccionar una cobranza/cuota con desvíos activos registrados (por ejemplo, Cuota 3 de 6 del Dto. 779/2026 con 3 desvíos vigentes), el usuario abría el desplegable **"Ver / Registrar Movimientos de Recuperos y Reservas"** y el contenedor aparecía completamente en blanco. 
* **Impacto operativo:** Imposibilidad de registrar recuperos de fondos hacia Fin Original, Reserva u otras obras desde la tarjeta de la cuota correspondiente.
* **Causa de desconcierto:** Las tarjetas que estaban al final de la página o que coincidían con el último registro evaluado podían funcionar, mientras que las anteriores fallaban silenciosamente sin arrojar excepción en consola.

---

### 3. Causa Raíz (Diagnóstico Técnico)
La interfaz procesa las cobranzas en dos etapas secuenciales dentro de la función de renderizado:

1. **Etapa 1 (Agregación y Filtros):** 
   Un bucle (`for q_id, group_cobros, _ in groups_list:`) recorre todas las cuotas para calcular métricas acumuladas, determinar el estado de distribución y consultar las colecciones `desvios_all` y `usos_r_all`. 
   * **El error:** Al finalizar este bucle y guardar la tarjeta en la lista filtrada (`filtered_groups.append({...})`), los arrays `desvios_all` y `usos_r_all` **no fueron empaquetados dentro del diccionario del objeto**.
2. **Etapa 2 (Renderizado Paginado):** 
   Un segundo bucle (`for item in page_items:`) dibuja las tarjetas en pantalla. Dentro del expander se ejecutaban las sentencias:
   ```python
   for d in desvios_all:
       ...
   for u in usos_r_all:
       ...
   ```
   Como `desvios_all` y `usos_r_all` no provenían de `item`, Python tomaba por defecto las variables residuales que quedaron vivas en el contexto local de la función al terminar la Etapa 1 (es decir, los datos de la **última cuota evaluada** en el dataset general). Si esa última cuota no tenía desvíos, las listas quedaban en `[]` y el expander no renderizaba nada.

---

### 4. Solución Aplicada (Hotfix)

Se corrigió la auto-contención de los datos en `components/tab_estado.py`:

1. **Empaquetado en la estructura de datos:**
   ```python
   filtered_groups.append({
       'q_id': q_id,
       'group_cobros': group_cobros,
       'monto_total_cobrado': monto_total_cobrado,
       'item_sin_dist': item_sin_dist,
       'item_fin_orig': item_fin_orig,
       'item_desvios': item_desvios,
       'item_en_reserva': item_en_reserva,
       'unified_desvios': unified_desvios,
       'desvios_all': desvios_all,   # <-- Incorporado
       'usos_r_all': usos_r_all      # <-- Incorporado
   })
   ```

2. **Extracción unívoca por tarjeta en el renderizado:**
   ```python
   for item in page_items:
       ...
       desvios_all = item['desvios_all']
       usos_r_all = item['usos_r_all']
   ```

3. **Manejo defensivo de estado vacío:**
   Se incorporó un aviso explicativo (`st.info`) dentro del desplegable para aquellos casos en que una cobranza legítimamente no posea desvíos, reservas ni fondos originales, evitando cajas vacías sin feedback:
   ```python
   tiene_movimientos = bool(desvios_all or usos_r_all or any(c.get('monto_fin_orig', 0) > 0 or c.get('monto_reserva', 0) > 0 for c in group_cobros))
   if not tiene_movimientos:
       st.info("ℹ️ Esta cobranza no posee desvíos, reservas ni pagos a Fin Original registrados para gestionar.")
   ```

---

### 5. Directrices de Arquitectura para el Decretómetro 2.0

Para evitar la repetición de este patrón en la nueva versión bimonetaria:

1. **Adopción de ViewModels / DTOs tipados:**
   Cada componente o tarjeta visual debe alimentarse exclusivamente de una estructura de datos cerrada (objeto de clase o `dataclass`/`pydantic`) que contenga el 100% de la información requerida para su renderizado.
2. **Prohibición de variables globales/leaked en bucles de UI:**
   Ningún componente interno (botones, inputs, desplegables) debe consumir variables que no hayan sido desempaquetadas explícitamente del objeto de la iteración actual (`item.desvios`, `item.usos_reserva`).
3. **Encapsulamiento del componente de tarjeta:**
   Refactorizar el dibujo de la tarjeta de cobranza a una función independiente pura (ej. `render_tarjeta_cobranza(cuota_view_model)`). Al modularizarlo en una función con parámetros estrictos, Python lanzará un error inmediato (`NameError`) si se intenta leer una variable fuera del alcance de esa tarjeta.
