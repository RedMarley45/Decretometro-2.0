import re

def update_tab_estado():
    with open('components/tab_estado.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update form_uso_fo_{cobro_id}
    # Replace form with container
    content = content.replace('with st.form(f"form_uso_fo_{cobro_id}", clear_on_submit=True):', 'with st.container():')
    content = content.replace('st.form_submit_button("Registrar Pago de Fin Original", type="primary")', 'st.button("Registrar Pago de Fin Original", type="primary", key=f"btn_fo_{cobro_id}")')
    
    # After success, clear keys
    success_block_fo = '''
                                                        st.session_state['success_msg_dist'] = "Pago a Fin Original registrado."
                                                        for k in [f"op_fo_pay_inp_{cobro_id}", f"chk_confirmar_fo_pay_sin_op_{cobro_id}"]:
                                                            if k in st.session_state:
                                                                del st.session_state[k]
                                                        st.rerun()'''
    content = re.sub(r'st\.session_state\[\'success_msg_dist\'\] = "Pago a Fin Original registrado\."\s*st\.rerun\(\)', success_block_fo.strip(), content)

    # Move op_fo_pay logic BEFORE other inputs in container to allow showing info
    op_input_fo = '''
                                            op_fo_pay = st.text_input("Número de Orden de Pago", key=f"op_fo_pay_inp_{cobro_id}")
                                            op_fo_pay = ''.join(filter(str.isdigit, op_fo_pay)) # force digits
                                            if op_fo_pay:
                                                usos_op = db.get_op_usage_details(op_fo_pay)
                                                if usos_op:
                                                    st.info("ℹ️ **Esta OP ya está vinculada a los siguientes pagos:**")
                                                    for u in usos_op:
                                                        st.info(f"- {u['origen']} por {utils.format_currency_ar(u['monto'])}")
'''
    
    # Remove old op_fo_pay
    content = re.sub(r'op_fo_pay = st\.text_input\("Número de Orden de Pago", key=f"op_fo_pay_inp_\{cobro_id\}"\)\n', '', content)
    # Insert new op_fo_pay at top of container
    content = content.replace('cc1, cc2 = st.columns(2)', op_input_fo + '                                            cc1, cc2 = st.columns(2)')

    # 2. Update form_uso_r_{cobro_id}
    content = content.replace('with st.form(f"form_uso_r_{cobro_id}", clear_on_submit=True):', 'with st.container():')
    content = content.replace('st.form_submit_button("Registrar Uso de Reserva", type="primary")', 'st.button("Registrar Uso de Reserva", type="primary", key=f"btn_uso_r_{cobro_id}")')

    success_block_r = '''
                                                        st.session_state['success_msg_dist'] = "Uso de reserva registrado."
                                                        for k in [f"op_uso_{cobro_id}", f"notes_uso_{cobro_id}", f"chk_confirmar_uso_sin_op_{cobro_id}", f"uso_obra_id_{cobro_id}", f"uso_gasto_id_sel_{cobro_id}", f"uso_gasto_prov_txt_{cobro_id}"]:
                                                            if k in st.session_state:
                                                                del st.session_state[k]
                                                        st.rerun()'''
    content = re.sub(r'st\.session_state\[\'success_msg_dist\'\] = "Uso de reserva registrado\."\s*st\.rerun\(\)', success_block_r.strip(), content)

    # Move op_uso to top and lock logic
    op_input_r = '''
                                            op_uso = st.text_input("Número de Orden de Pago (Uso Reserva)", key=f"op_uso_{cobro_id}")
                                            op_uso = ''.join(filter(str.isdigit, op_uso))
                                            
                                            op_locked_obra = None
                                            op_locked_gasto = None
                                            
                                            if op_uso:
                                                usos_op = db.get_op_usage_details(op_uso)
                                                if usos_op:
                                                    st.info("ℹ️ **Esta OP ya está vinculada a los siguientes pagos:**")
                                                    for u in usos_op:
                                                        st.info(f"- {u['origen']} por {utils.format_currency_ar(u['monto'])}")
                                                    op_info = db.get_op_info(op_uso)
                                                    if op_info:
                                                        if op_info['obra_id']: op_locked_obra = op_info['obra_id']
                                                        if op_info['gasto_id']: op_locked_gasto = op_info['gasto_id']
                                                        st.warning("⚠️ **OP ya utilizada:** El destino (Obra/Gasto) ha sido bloqueado para coincidir con el original. Si hay un error, debe eliminar los pagos previos de esta OP.")

                                            cc1, cc2, cc3 = st.columns(3)
'''
    # Remove old op_uso
    content = re.sub(r'op_uso = st\.text_input\("Número de Orden de Pago \(Uso Reserva\)", key=f"op_uso_\{cobro_id\}"\)\n', '', content)
    # Insert new op_uso at top
    content = content.replace('cc1, cc2, cc3 = st.columns(3)', op_input_r)

    # Adjust Selectbox for tipo_uso to read from lock
    tipo_uso_logic = '''
                                            tipo_opciones = ["fin_original", "obra_catalogo", "gasto_fun"]
                                            index_tipo = 0
                                            if op_locked_obra: index_tipo = 1
                                            elif op_locked_gasto: index_tipo = 2
                                            tipo_uso = cc3.selectbox("¿Hacia dónde va?", tipo_opciones, index=index_tipo, disabled=(op_locked_obra is not None or op_locked_gasto is not None), format_func=lambda x: "Fin original" if x == "fin_original" else ("Obra (Catálogo)" if x == "obra_catalogo" else "Gasto de Funcionamiento (FUN)"))
'''
    content = re.sub(r'tipo_uso = cc3\.selectbox\("¿Hacia dónde va\?", \["fin_original", "obra_catalogo", "gasto_fun"\], format_func=lambda x: "Fin original" if x == "fin_original" else \("Obra \(Catálogo\)" if x == "obra_catalogo" else "Gasto de Funcionamiento \(FUN\)"\)\)\n', tipo_uso_logic.lstrip('\n'), content)

    # Adjust obra and gasto selections to use lock
    content = content.replace('nd_obra_id = st.selectbox("Seleccione la Obra Destino", options=list(opc_obras.keys()), format_func=lambda x: opc_obras[x], key=f"uso_obra_id_{cobro_id}")',
                              'idx_o = list(opc_obras.keys()).index(op_locked_obra) if op_locked_obra in opc_obras else 0\n                                                nd_obra_id = st.selectbox("Seleccione la Obra Destino", options=list(opc_obras.keys()), index=idx_o, disabled=(op_locked_obra is not None), format_func=lambda x: opc_obras[x], key=f"uso_obra_id_{cobro_id}")')

    content = content.replace('gasto_id_sel = st.selectbox("Seleccione el Gasto de Funcionamiento (FUN)", options=list(opc_gastos.keys()), format_func=lambda x: opc_gastos[x], key=f"uso_gasto_id_sel_{cobro_id}")',
                              'idx_g = list(opc_gastos.keys()).index(op_locked_gasto) if op_locked_gasto in opc_gastos else 0\n                                                gasto_id_sel = st.selectbox("Seleccione el Gasto de Funcionamiento (FUN)", options=list(opc_gastos.keys()), index=idx_g, disabled=(op_locked_gasto is not None), format_func=lambda x: opc_gastos[x], key=f"uso_gasto_id_sel_{cobro_id}")')

    with open('components/tab_estado.py', 'w', encoding='utf-8') as f:
        f.write(content)


def update_tab_distribuir():
    with open('components/tab_distribuir.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Move nd_op to top of the form, similar to tab_estado
    op_input_desv = '''
                    nd_op = st.text_input("Número de Orden de Pago (Desvío)", key=f"nd_op_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
                    nd_op = ''.join(filter(str.isdigit, nd_op))
                    
                    op_locked_obra = None
                    op_locked_gasto = None
                    
                    if nd_op:
                        usos_op = db.get_op_usage_details(nd_op)
                        if usos_op:
                            st.info("ℹ️ **Esta OP ya está vinculada a los siguientes pagos:**")
                            for u in usos_op:
                                st.info(f"- {u['origen']} por {utils.format_currency_ar(u['monto'])}")
                            op_info = db.get_op_info(nd_op)
                            if op_info:
                                if op_info['obra_id']: op_locked_obra = op_info['obra_id']
                                if op_info['gasto_id']: op_locked_gasto = op_info['gasto_id']
                                st.warning("⚠️ **OP ya utilizada:** El destino ha sido bloqueado. Si hay un error, elimine los pagos previos.")

                    tipo_opciones_d = ["Hacia Obra (Catálogo)", "Hacia Gasto de Funcionamiento (FUN)"]
                    index_tipo_d = 0
                    if op_locked_obra: index_tipo_d = 0
                    elif op_locked_gasto: index_tipo_d = 1
                    
                    tipo_desvio = st.radio("Destino del Desvío:", tipo_opciones_d, index=index_tipo_d, disabled=(op_locked_obra is not None or op_locked_gasto is not None), key=f"tipo_desvio_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))
'''

    content = re.sub(r'nd_op = st\.text_input\("Número de Orden de Pago \(Desvío\)", key=f"nd_op_\{c_sel_id\}", on_change=keep_expander_open, args=\(c_sel_id,\)\)\n', '', content)
    # Note: Will use string replace instead due to escaping

    # Do it with string replace
    old_tipo = 'tipo_desvio = st.radio("Destino del Desvío:", ["Hacia Obra (Catálogo)", "Hacia Gasto de Funcionamiento (FUN)"], key=f"tipo_desvio_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))'
    content = content.replace(old_tipo, op_input_desv.strip())

    content = content.replace('nd_obra_id = st.selectbox("Seleccione la Obra Destino", options=list(opc_obras.keys()), format_func=lambda x: opc_obras[x], key=f"nd_obra_id_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))',
                              'idx_o = list(opc_obras.keys()).index(op_locked_obra) if op_locked_obra in opc_obras else 0\n                            nd_obra_id = st.selectbox("Seleccione la Obra Destino", options=list(opc_obras.keys()), index=idx_o, disabled=(op_locked_obra is not None), format_func=lambda x: opc_obras[x], key=f"nd_obra_id_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))')

    content = content.replace('gasto_id_sel = st.selectbox("Seleccione el Gasto de Funcionamiento (FUN)", options=list(opc_gastos.keys()), format_func=lambda x: opc_gastos[x], key=f"nd_gasto_id_sel_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))',
                              'idx_g = list(opc_gastos.keys()).index(op_locked_gasto) if op_locked_gasto in opc_gastos else 0\n                        gasto_id_sel = st.selectbox("Seleccione el Gasto de Funcionamiento (FUN)", options=list(opc_gastos.keys()), index=idx_g, disabled=(op_locked_gasto is not None), format_func=lambda x: opc_gastos[x], key=f"nd_gasto_id_sel_{c_sel_id}", on_change=keep_expander_open, args=(c_sel_id,))')

    with open('components/tab_distribuir.py', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    update_tab_estado()
    update_tab_distribuir()
