"""
db_core - Núcleo Transaccional Modular de Decretómetro 2.0 (Fase 3)
Re-exporta todas las entidades y funciones de los repositorios especializados
garantizando compatibilidad binaria 100% con la fachada database.py.
"""
from contextlib import contextmanager
from db_core.connection import (
    DB_PATH, TOLERANCE, DESTINO_FIN_ORIGINAL, DESTINO_RESERVA, DESTINO_OTRA_OBRA,
    _local_session, get_db_path, get_connection, db_session
)
from db_core.migrations import (
    init_db, _instalar_triggers_auditoria
)
from db_core.repo_auditoria import (
    _validar_op_o_nota_db, get_op_info, get_op_usage_count, get_op_usage_details,
    register_or_update_op, get_audit_log, get_historial_cambios_registro
)
from db_core.repo_catalogos import (
    get_monedas_indices, get_moneda_indice, add_moneda_indice, update_moneda_indice,
    get_ultima_cotizacion, get_ultima_cotizacion_info,
    add_proveedor_obra, get_proveedores_obras, get_proveedor_obra, update_proveedor_obra,
    update_proveedor_obra_estado, delete_proveedor_obra,
    add_proveedor_funcionamiento, get_proveedores_funcionamiento, get_proveedor_funcionamiento,
    update_proveedor_funcionamiento, update_proveedor_funcionamiento_estado,
    delete_proveedor_funcionamiento, get_todos_proveedores,
    add_gasto_funcionamiento, get_gastos_funcionamiento, get_gasto_funcionamiento,
    get_gasto_funcionamiento_by_expediente, update_gasto_funcionamiento,
    update_gasto_funcionamiento_estado, update_gasto_funcionamiento_proveedor,
    delete_gasto_funcionamiento
)
from db_core.repo_habituales import (
    set_monto_funcionamiento_anio, get_aportes_funcionamiento, registrar_cobro_funcionamiento,
    reset_cobro_funcionamiento, delete_anio_funcionamiento,
    add_aporte_sueldo, get_aportes_sueldo, registrar_cobro_sueldo, delete_aporte_sueldo,
    update_aporte_sueldo, renunciar_aporte_sueldo,
    add_aporte_sac, get_aportes_sac, registrar_cobro_sac, delete_aporte_sac,
    update_aporte_sac, renunciar_aporte_sac
)
from db_core.repo_decretos import (
    add_decreto, get_decretos, get_decreto, check_expediente_exists, update_decreto,
    delete_decreto, update_estado_decreto, check_estado_decreto, check_estado_decreto_by_cuota,
    add_cuota, get_cuotas_by_decreto, get_cuota, get_total_cobrado_por_cuota,
    update_cuota_estimacion, get_due_date,
    get_decretos_by_obra, get_obras_by_decreto, add_decreto_obras, update_decreto_details_for_solicitud,
    add_solicitud, update_solicitud, delete_solicitud, get_solicitudes, get_solicitud,
    get_solicitud_por_decreto, update_estado_solicitud, get_obras_sin_solicitud,
    add_prestamo, delete_prestamo, update_estado_prestamo, get_prestamos, add_recupero, delete_recupero
)
from db_core.repo_cobros import (
    _calcular_saldos_cobro_tx, add_cobro, get_all_cobros, get_cobros_by_cuota, get_cobro,
    delete_cobro, get_distribucion_by_cobro, upsert_distribucion,
    get_cobros_con_resumen_distribucion,
    add_fin_original_uso, update_fin_original_uso, delete_fin_original_uso,
    get_fin_original_usos_by_cobro
)
from db_core.repo_obras import (
    add_obra, update_obra, delete_obra, get_obras, get_obra, get_obra_by_expediente,
    update_monto_contrato_obra, add_obra_adicional, get_obra_adicionales, delete_obra_adicional,
    get_resumen_contrato_obra, get_pagos_detalle_por_obra, check_sobrepago_obra,
    get_total_pagado_obra, get_tope_recupero,
    get_pagos_fondos_propios, add_pago_fondos_propios, delete_pago_fondos_propios
)
from db_core.repo_convenios import (
    add_convenio, update_convenio, delete_convenio, get_convenios, get_convenio,
    update_estado_convenio, check_estado_convenio, check_estado_convenio_by_solicitud,
    get_convenios_by_obra, add_obra_to_convenio, remove_obra_from_convenio, get_obras_by_convenio,
    add_solicitud_convenio, update_solicitud_convenio, delete_solicitud_convenio,
    get_solicitudes_by_convenio, get_solicitudes_convenio_pendientes, get_solicitud_convenio,
    get_resumen_control_convenio, get_cobros_by_convenio, get_kpis_convenios_global
)
from db_core.repo_desvios_reservas import (
    add_desvio, update_desvio, delete_desvio, get_desvios_by_cobro,
    add_reserva_uso, update_reserva_uso, delete_reserva_uso, get_reserva_usos_by_cobro,
    get_saldo_reserva_cobro, get_reserva_usos_prestamos_activos,
    add_desvio_recupero, add_reserva_uso_recupero, get_recuperos_by_desvio,
    get_recuperos_by_reserva_uso, get_recuperos_by_prestamo,
    add_recupero_fondos_propios, delete_recupero_fondos_propios, get_recuperos_fondos_propios,
    get_recuperos_fondos_propios_by_cobro, get_recuperos_by_cobro,
    get_deuda_desvios_by_decreto, get_deudas_obras_propias, get_deudas_consolidadas,
    get_obras_propias_nombres, get_desvios_activos_completos, get_historial_desvios,
    get_desvios_por_deudora, get_desvios_por_acreedora, get_todas_obras_para_trazabilidad,
    get_trazabilidad_fuentes_por_obra, _DESVIOS_SELECT_INICIAL, _DESVIOS_SELECT_RESERVA
)
from db_core.repo_compensaciones import (
    obtener_detalles_compensacion_grupo, delete_desvio_recupero, delete_reserva_uso_recupero,
    update_desvio_recupero, update_reserva_uso_recupero
)

# Definición de __all__ incluyendo símbolos públicos, constantes y helpers privados requeridos por Argon
__all__ = [
    'contextmanager',
    'DB_PATH', 'TOLERANCE', 'DESTINO_FIN_ORIGINAL', 'DESTINO_RESERVA', 'DESTINO_OTRA_OBRA',
    '_local_session', 'get_db_path', 'get_connection', 'db_session',
    'init_db', '_instalar_triggers_auditoria',
    '_validar_op_o_nota_db', 'get_op_info', 'get_op_usage_count', 'get_op_usage_details',
    'register_or_update_op', 'get_audit_log', 'get_historial_cambios_registro',
    'get_monedas_indices', 'get_moneda_indice', 'add_moneda_indice', 'update_moneda_indice',
    'get_ultima_cotizacion', 'get_ultima_cotizacion_info',
    'add_proveedor_obra', 'get_proveedores_obras', 'get_proveedor_obra', 'update_proveedor_obra',
    'update_proveedor_obra_estado', 'delete_proveedor_obra',
    'add_proveedor_funcionamiento', 'get_proveedores_funcionamiento', 'get_proveedor_funcionamiento',
    'update_proveedor_funcionamiento', 'update_proveedor_funcionamiento_estado',
    'delete_proveedor_funcionamiento', 'get_todos_proveedores',
    'add_gasto_funcionamiento', 'get_gastos_funcionamiento', 'get_gasto_funcionamiento',
    'get_gasto_funcionamiento_by_expediente', 'update_gasto_funcionamiento',
    'update_gasto_funcionamiento_estado', 'update_gasto_funcionamiento_proveedor',
    'delete_gasto_funcionamiento',
    'set_monto_funcionamiento_anio', 'get_aportes_funcionamiento', 'registrar_cobro_funcionamiento',
    'reset_cobro_funcionamiento', 'delete_anio_funcionamiento',
    'add_aporte_sueldo', 'get_aportes_sueldo', 'registrar_cobro_sueldo', 'delete_aporte_sueldo',
    'update_aporte_sueldo', 'renunciar_aporte_sueldo',
    'add_aporte_sac', 'get_aportes_sac', 'registrar_cobro_sac', 'delete_aporte_sac',
    'update_aporte_sac', 'renunciar_aporte_sac',
    'add_decreto', 'get_decretos', 'get_decreto', 'check_expediente_exists', 'update_decreto',
    'delete_decreto', 'update_estado_decreto', 'check_estado_decreto', 'check_estado_decreto_by_cuota',
    'add_cuota', 'get_cuotas_by_decreto', 'get_cuota', 'get_total_cobrado_por_cuota',
    'update_cuota_estimacion', 'get_due_date',
    'get_decretos_by_obra', 'get_obras_by_decreto', 'add_decreto_obras', 'update_decreto_details_for_solicitud',
    'add_solicitud', 'update_solicitud', 'delete_solicitud', 'get_solicitudes', 'get_solicitud',
    'get_solicitud_por_decreto', 'update_estado_solicitud', 'get_obras_sin_solicitud',
    'add_prestamo', 'delete_prestamo', 'update_estado_prestamo', 'get_prestamos', 'add_recupero', 'delete_recupero',
    '_calcular_saldos_cobro_tx', 'add_cobro', 'get_all_cobros', 'get_cobros_by_cuota', 'get_cobro',
    'delete_cobro', 'get_distribucion_by_cobro', 'upsert_distribucion',
    'get_cobros_con_resumen_distribucion',
    'add_fin_original_uso', 'update_fin_original_uso', 'delete_fin_original_uso',
    'get_fin_original_usos_by_cobro',
    'add_obra', 'update_obra', 'delete_obra', 'get_obras', 'get_obra', 'get_obra_by_expediente',
    'update_monto_contrato_obra', 'add_obra_adicional', 'get_obra_adicionales', 'delete_obra_adicional',
    'get_resumen_contrato_obra', 'get_pagos_detalle_por_obra', 'check_sobrepago_obra',
    'get_total_pagado_obra', 'get_tope_recupero',
    'get_pagos_fondos_propios', 'add_pago_fondos_propios', 'delete_pago_fondos_propios',
    'add_convenio', 'update_convenio', 'delete_convenio', 'get_convenios', 'get_convenio',
    'update_estado_convenio', 'check_estado_convenio', 'check_estado_convenio_by_solicitud',
    'get_convenios_by_obra', 'add_obra_to_convenio', 'remove_obra_from_convenio', 'get_obras_by_convenio',
    'add_solicitud_convenio', 'update_solicitud_convenio', 'delete_solicitud_convenio',
    'get_solicitudes_by_convenio', 'get_solicitudes_convenio_pendientes', 'get_solicitud_convenio',
    'get_resumen_control_convenio', 'get_cobros_by_convenio', 'get_kpis_convenios_global',
    'add_desvio', 'update_desvio', 'delete_desvio', 'get_desvios_by_cobro',
    'add_reserva_uso', 'update_reserva_uso', 'delete_reserva_uso', 'get_reserva_usos_by_cobro',
    'get_saldo_reserva_cobro', 'get_reserva_usos_prestamos_activos',
    'add_desvio_recupero', 'add_reserva_uso_recupero', 'get_recuperos_by_desvio',
    'get_recuperos_by_reserva_uso', 'get_recuperos_by_prestamo',
    'add_recupero_fondos_propios', 'delete_recupero_fondos_propios', 'get_recuperos_fondos_propios',
    'get_recuperos_fondos_propios_by_cobro', 'get_recuperos_by_cobro',
    'get_deuda_desvios_by_decreto', 'get_deudas_obras_propias', 'get_deudas_consolidadas',
    'get_obras_propias_nombres', 'get_desvios_activos_completos', 'get_historial_desvios',
    'get_desvios_por_deudora', 'get_desvios_por_acreedora', 'get_todas_obras_para_trazabilidad',
    'get_trazabilidad_fuentes_por_obra', '_DESVIOS_SELECT_INICIAL', '_DESVIOS_SELECT_RESERVA',
    'obtener_detalles_compensacion_grupo', 'delete_desvio_recupero', 'delete_reserva_uso_recupero',
    'update_desvio_recupero', 'update_reserva_uso_recupero'
]
