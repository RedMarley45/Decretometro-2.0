import database as db
import trazabilidad_graph as tg
import json

cobro_id = 636
codigo_mermaid = tg.generar_mermaid_trazabilidad(cobro_id)
codigo_js = json.dumps(codigo_mermaid)

html_code = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            margin: 0;
            padding: 0;
            background-color: #ffffff;
        }}
        #mermaid-container {{
            background: #ffffff;
            padding: 15px;
            display: flex;
            justify-content: center;
            align-items: center;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}
        .error-box {{
            color: #721c24;
            background-color: #f8d7da;
            border: 1px solid #f5c6cb;
            padding: 15px;
            border-radius: 6px;
            font-family: 'Segoe UI', system-ui, sans-serif;
            font-size: 14px;
            margin: 10px;
        }}
    </style>
</head>
<body>
    <!-- Contenedor del Grafo -->
    <div id="mermaid-container">
        <div id="mermaid-graph-div" class="mermaid">
            <!-- Se poblará dinámicamente mediante JavaScript -->
        </div>
    </div>

    <!-- Panel de Depuración en Pantalla -->
    <div id="debug-log-panel" style="margin: 15px; padding: 10px; background-color: #f8f9fa; border: 1px dashed #ced4da; border-radius: 4px; font-family: monospace; font-size: 11px; color: #495057;">
        <div style="font-weight: bold; margin-bottom: 5px; border-bottom: 1px solid #dee2e6; padding-bottom: 3px; display: flex; justify-content: space-between;">
            <span>📋 LOGS DE DEPURACIÓN DEL MAPA (Cobro {cobro_id}):</span>
            <span id="log-status" style="color: #0d6efd;">Cargando...</span>
        </div>
        <div id="debug-log-lines" style="max-height: 150px; overflow-y: auto;">
            <!-- Logs aparecerán aquí -->
        </div>
    </div>

    <script>
        var logLines = null;
        var logStatus = null;
        
        function logToScreen(msg) {{
            logLines = document.getElementById('debug-log-lines');
            logStatus = document.getElementById('log-status');
            if (logLines) {{
                var div = document.createElement('div');
                div.style.borderBottom = "1px solid #f1f3f5";
                div.style.padding = "2px 0";
                div.textContent = "[" + new Date().toLocaleTimeString() + "] " + msg;
                logLines.appendChild(div);
                logLines.scrollTop = logLines.scrollHeight;
            }}
        }}

        function setStatus(text, color) {{
            logStatus = document.getElementById('log-status');
            if (logStatus) {{
                logStatus.textContent = text;
                if (color) logStatus.style.color = color;
            }}
        }}

        // Función de redimensionamiento del iframe de Streamlit
        function resize() {{
            var container = document.getElementById('mermaid-container');
            var debugPanel = document.getElementById('debug-log-panel');
            if (container) {{
                var height = container.scrollHeight + (debugPanel ? debugPanel.scrollHeight : 0) + 60;
                window.parent.postMessage({{
                    type: 'streamlit:setFrameHeight',
                    height: height
                }}, '*');
            }}
        }}

        // Registrar inmediatamente el error handler global en fase de captura para atrapar fallos de CDN
        window.addEventListener('error', function(e) {{
            var msg = "GLOBAL ERROR: " + e.message + " at " + e.filename + ":" + e.lineno;
            logToScreen(msg);
            setStatus("ERROR", "#dc3545");
            
            var container = document.getElementById('mermaid-container');
            if (container) {{
                container.innerHTML = '<div class="error-box">' +
                    '<b>Error en el mapa de fondos:</b><br>' +
                    'No se pudo cargar o renderizar el gráfico. Es posible que los servidores de gráficos estén bloqueados o no tenga acceso a internet.<br>' +
                    '<small style="color:#721c24; display:block; margin-top:5px;">Detalle: ' + e.message + '</small>' +
                    '</div>';
            }}
            resize();
        }}, true);
        
        // CDNs redundantes para la carga de Mermaid v9.4.3
        var cdns = [
            "https://cdn.jsdelivr.net/npm/mermaid@9.4.3/dist/mermaid.min.js",
            "https://cdnjs.cloudflare.com/ajax/libs/mermaid/9.4.3/mermaid.min.js",
            "https://unpkg.com/mermaid@9.4.3/dist/mermaid.min.js"
        ];
        var currentCdnIdx = 0;

        function loadMermaid() {{
            logToScreen("Intentando cargar CDN: " + cdns[currentCdnIdx]);
            setStatus("Cargando CDN (" + (currentCdnIdx+1) + "/" + cdns.length + ")...", "#0d6efd");
            
            var script = document.createElement('script');
            script.src = cdns[currentCdnIdx];
            script.onload = function() {{
                logToScreen("CDN cargado con éxito: " + cdns[currentCdnIdx]);
                setStatus("CDN Cargado, Inicializando...", "#198754");
                initMermaid();
            }};
            script.onerror = function() {{
                logToScreen("Fallo al cargar CDN: " + cdns[currentCdnIdx]);
                currentCdnIdx++;
                if (currentCdnIdx >= cdns.length) {{
                    logToScreen("TODOS los CDNs fallaron!");
                    setStatus("FALLA DE RED", "#dc3545");
                    var container = document.getElementById('mermaid-container');
                    if (container) {{
                        container.innerHTML = '<div class="error-box">' +
                            '<b>No se pudo conectar con los servidores de visualización:</b><br>' +
                            'Todos los CDNs de gráficos (jsDelivr, Cloudflare, unpkg) fallaron al cargar. ' +
                            'Por favor verifique si tiene conexión a internet o políticas de red.' +
                            '</div>';
                    }}
                    resize();
                    return;
                }}
                loadMermaid(); // Intentar con el siguiente CDN
            }};
            document.head.appendChild(script);
        }}

        function initMermaid() {{
            try {{
                var mermaidCode = {codigo_js};
                logToScreen("Código Mermaid cargado.");
                
                var targetDiv = document.getElementById('mermaid-graph-div');
                if (targetDiv) {{
                    targetDiv.textContent = mermaidCode;
                }}

                mermaid.initialize({{ 
                    startOnLoad: false,
                    theme: 'neutral',
                    securityLevel: 'loose',
                    flowchart: {{ 
                        useMaxWidth: false, 
                        htmlLabels: true, 
                        curve: 'basis' 
                        }}
                }});
                
                logToScreen("Llamando a mermaid.init()...");
                mermaid.init(undefined, document.querySelectorAll('.mermaid'));
                logToScreen("mermaid.init() ejecutado con éxito.");
                setStatus("Renderizado Completado", "#198754");
                setTimeout(resize, 400);
            }} catch (err) {{
                logToScreen("EXCEPCIÓN EN initMermaid: " + err.message + "\nStack: " + err.stack);
                setStatus("ERROR AL RENDERIZAR", "#dc3545");
                var container = document.getElementById('mermaid-container');
                if (container) {{
                    container.innerHTML = '<div class="error-box">' +
                        '<b>Error al inicializar el gráfico:</b><br>' +
                        err.message +
                        '</div>';
                }}
                resize();
            }}
        }}

        // Ejecutar la carga de Mermaid lo antes posible
        setTimeout(function() {{
            logToScreen("readyState: " + document.readyState);
            if (document.readyState === "complete" || document.readyState === "interactive") {{
                loadMermaid();
            }} else {{
                window.addEventListener('load', loadMermaid);
            }}
        }}, 100);
    </script>
</body>
</html>
"""

open("test_output.html", "w", encoding="utf-8").write(html_code)
print("Saved to test_output.html")
