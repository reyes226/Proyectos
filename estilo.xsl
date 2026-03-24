<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
<xsl:template match="/">
<html>
<head>
    <title>NutriCalc Pro - Edición y Detalle</title>
    <style>
        :root { --p: #4a90e2; --s: #50e3c2; --d: #ff5a5f; --bg: #f4f7f9; --dark: #2c3e50; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); margin: 0; padding-bottom: 50px; }
        
        /* Notificaciones (Toast) */
        #toast { position: fixed; bottom: 20px; right: 20px; background: var(--dark); color: white; padding: 12px 25px; border-radius: 8px; display: none; z-index: 1000; box-shadow: 0 4px 12px rgba(0,0,0,0.2); animation: slideUp 0.3s; }
        @keyframes slideUp { from { transform: translateY(100px); } to { transform: translateY(0); } }

        .sync-zone { background: var(--dark); color: white; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; }
        .tabs { display: flex; background: white; box-shadow: 0 2px 10px rgba(0,0,0,0.1); position: sticky; top: 0; z-index: 100; }
        .tab-btn { padding: 20px; cursor: pointer; border: none; background: none; font-weight: bold; flex: 1; transition: 0.3s; border-bottom: 3px solid transparent; font-size: 15px; }
        .tab-btn.active { border-bottom: 3px solid var(--p); color: var(--p); }
        
        .content-section { display: none; padding: 30px; max-width: 1100px; margin: auto; }
        .content-section.active { display: block; }

        /* Tarjetas Detalladas */
        .card { background: white; padding: 25px; border-radius: 15px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); margin-bottom: 25px; }
        .recipe-detail { border-top: 1px solid #eee; margin-top: 15px; padding-top: 15px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        
        .grid-form { display: grid; grid-template-columns: 1.2fr 1fr; gap: 30px; }
        input, textarea, select { width: 100%; padding: 12px; border: 1px solid #e0e0e0; border-radius: 8px; margin-top: 8px; box-sizing: border-box; }
        
        .btn { padding: 10px 18px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; color: white; transition: 0.2s; margin-top: 10px; }
        .btn-p { background: var(--p); } .btn-d { background: var(--d); } .btn-s { background: var(--s); color: var(--dark); }

        .macro-badge { padding: 5px 10px; border-radius: 15px; color: white; font-size: 11px; font-weight: bold; display: inline-block; margin-right: 5px; }
        ul, ol { padding-left: 20px; font-size: 14px; color: #444; }
    </style>
</head>
<body onload="inicializarApp()">

    <div id="toast"></div>

    <div class="sync-zone">
        <span><b>NutriCalc</b> | Datos Sincronizados</span>
        <div>
            <button class="btn btn-s" onclick="document.getElementById('import-file').click()">📂 Cargar XML</button>
            <input type="file" id="import-file" style="display:none" accept=".xml" onchange="importarXML(this)"/>
            
            <button class="btn btn-s" style="background:#fff; color:#2c3e50;" onclick="descargarXML()">📥 Exportar XML</button>
        </div>
    </div>

    <nav class="tabs">
        <button id="btn-view" class="tab-btn active" onclick="switchTab('tab-view', this)">📋 Mis Recetas</button>
        <button id="btn-create" class="tab-btn" onclick="switchTab('tab-create', this)">➕ Crear/Editar</button>
        <button id="btn-db" class="tab-btn" onclick="switchTab('tab-db', this)">🍎 Alimentos</button>
    </nav>

    <section id="tab-view" class="content-section active">
        <h1>Mi Recetario</h1>
        <div id="recipe-list"></div>
    </section>

    <section id="tab-create" class="content-section">
        <div class="card">
            <h2 id="form-title">Nueva Receta</h2>
            <div class="grid-form">
                <div>
                    <label>Título</label><input type="text" id="r-titulo"/>
                    <label>Descripción</label><textarea id="r-desc" rows="2"></textarea>
                    
                    <h3>Ingredientes</h3>
                    <div style="display:grid; grid-template-columns: 2fr 1fr auto; gap:8px; align-items:end;">
                        <select id="r-ing-select"></select>
                        <input type="number" id="r-ing-cant" value="100"/>
                        <button class="btn btn-p" onclick="addIngToRecipe()">+</button>
                    </div>
                    <ul id="list-ingredientes-receta"></ul>
                </div>

                <div>
                    <h3>Utensilios</h3>
                    <div style="display:flex; gap:8px;">
                        <input type="text" id="u-nombre" placeholder="Nombre..."/>
                        <button class="btn btn-s" onclick="addToList('u-nombre', tempUtensilios, 'list-utensilios')">+</button>
                    </div>
                    <ul id="list-utensilios"></ul>

                    <h3>Pasos</h3>
                    <div style="display:flex; gap:8px;">
                        <textarea id="p-nombre" rows="1"></textarea>
                        <button class="btn btn-s" onclick="addToList('p-nombre', tempPasos, 'list-pasos')">+</button>
                    </div>
                    <ul id="list-pasos"></ul>
                </div>
            </div>
            <button id="btn-save-recipe" class="btn btn-p" style="width:100%; margin-top:30px; font-size:18px;" onclick="guardarReceta()">💾 Guardar Receta</button>
            <button id="btn-cancel-edit" class="btn btn-d" style="width:100%; display:none;" onclick="cancelarEdicion()">Cancelar Edición</button>
        </div>
    </section>

    <section id="tab-db" class="content-section">
        <div class="card">
            <h2>Base de Datos de Alimentos</h2>
            <div class="grid-form" style="grid-template-columns: 2fr repeat(3, 1fr);">
                <div><label>Nombre</label><input type="text" id="db-n"/></div>
                <div><label>Prot (g)</label><input type="number" id="db-pro" oninput="previewCal()"/></div>
                <div><label>Carb (g)</label><input type="number" id="db-car" oninput="previewCal()"/></div>
                <div><label>Gras (g)</label><input type="number" id="db-gra" oninput="previewCal()"/></div>
            </div>
            <p id="cal-preview" style="font-weight:bold; color:var(--p); margin-top:10px;">Calorías: 0 kcal</p>
            <button class="btn btn-s" onclick="saveIngToDB()">Registrar Alimento</button>
        </div>
        <div id="db-list"></div>
    </section>

    <script type="text/javascript">
    //<![CDATA[
        let DB_INGREDIENTES = {};
        let RECETAS = [];
        let tempUtensilios = [];
        let tempPasos = [];
        let tempIngredientes = [];
        let editId = null; // Para saber si estamos editando o creando

        function inicializarApp() {
            cargarDeLocalStorage();
            actualizarSelects();
            renderRecetas();
            renderDB();
        }


        function switchTab(id, el) {
            document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(id).classList.add('active');
            el.classList.add('active');
        }

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.innerText = msg; t.style.display = 'block';
            setTimeout(() => t.style.display = 'none', 3000);
        }

        function previewCal() {
            const p = parseFloat(document.getElementById('db-pro').value) || 0;
            const c = parseFloat(document.getElementById('db-car').value) || 0;
            const g = parseFloat(document.getElementById('db-gra').value) || 0;
            document.getElementById('cal-preview').innerText = `Calorías: ${((p*4)+(c*4)+(g*9)).toFixed(1)} kcal`;
        }

        // --- GESTIÓN DB ---
        function saveIngToDB() {
            const n = document.getElementById('db-n').value.toLowerCase().trim();
            if(!n) return;
            const p = parseFloat(document.getElementById('db-pro').value) || 0;
            const c = parseFloat(document.getElementById('db-car').value) || 0;
            const g = parseFloat(document.getElementById('db-gra').value) || 0;

            DB_INGREDIENTES[n] = { pro:p, car:c, gra:g, cal: (p*4)+(c*4)+(g*9) };
            guardarEnLocalStorage();
            actualizarSelects();
            renderDB();
            showToast("Alimento registrado correctamente");
            ['db-n','db-pro','db-car','db-gra'].forEach(id => document.getElementById(id).value = "");
        }

        function renderDB() {
            let h = "";
            Object.keys(DB_INGREDIENTES).sort().forEach(n => {
                const i = DB_INGREDIENTES[n];
                h += `<div class="card" style="padding:10px; display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <span><b>${n.toUpperCase()}</b>: ${i.cal.toFixed(1)} kcal</span>
                    <button class="btn-d" onclick="deleteFromDB('${n}')">Eliminar</button>
                </div>`;
            });
            document.getElementById('db-list').innerHTML = h;
        }

        function deleteFromDB(n) {
            delete DB_INGREDIENTES[n];
            guardarEnLocalStorage(); actualizarSelects(); renderDB();
        }

        // --- GESTIÓN RECETAS (CREAR Y EDITAR) ---
        function addToList(id, arr, listId) {
            const v = document.getElementById(id).value.trim();
            if(!v) return;
            arr.push(v);
            document.getElementById(listId).innerHTML += `<li>${v}</li>`;
            document.getElementById(id).value = "";
        }

        function addIngToRecipe() {
            const n = document.getElementById('r-ing-select').value;
            const c = parseFloat(document.getElementById('r-ing-cant').value);
            if(!n || !c) return;
            tempIngredientes.push({ nombre: n, cant: c });
            document.getElementById('list-ingredientes-receta').innerHTML += `<li>${n} (${c}g)</li>`;
        }

        function editarReceta(id) {
            const r = RECETAS.find(rec => rec.id === id);
            if(!r) return;
            
            editId = id;
            document.getElementById('form-title').innerText = "Editando: " + r.titulo;
            document.getElementById('r-titulo').value = r.titulo;
            document.getElementById('r-desc').value = r.desc;
            
            tempUtensilios = [...r.utensilios];
            tempPasos = [...r.pasos];
            tempIngredientes = [...r.ingredientes];

            document.getElementById('list-utensilios').innerHTML = tempUtensilios.map(u => `<li>${u}</li>`).join("");
            document.getElementById('list-pasos').innerHTML = tempPasos.map(p => `<li>${p}</li>`).join("");
            document.getElementById('list-ingredientes-receta').innerHTML = tempIngredientes.map(i => `<li>${i.nombre} (${i.cant}g)</li>`).join("");
            
            document.getElementById('btn-cancel-edit').style.display = 'block';
            switchTab('tab-create', document.getElementById('btn-create'));
        }

        function cancelarEdicion() {
            editId = null;
            document.getElementById('form-title').innerText = "Nueva Receta";
            document.getElementById('btn-cancel-edit').style.display = 'none';
            // Limpiar campos...
            resetForm();
            switchTab('tab-view', document.getElementById('btn-view'));
        }

        function resetForm() {
            tempUtensilios = []; tempPasos = []; tempIngredientes = [];
            ['r-titulo','r-desc','u-nombre','p-nombre'].forEach(id => document.getElementById(id).value = "");
            ['list-utensilios','list-pasos','list-ingredientes-receta'].forEach(id => document.getElementById(id).innerHTML = "");
        }

        function guardarReceta() {
            const t = document.getElementById('r-titulo').value.trim();
            if(!t || tempIngredientes.length === 0) return alert("Faltan datos");

            let nut = { p:0, c:0, g:0 };
            tempIngredientes.forEach(i => {
                const info = DB_INGREDIENTES[i.nombre];
                const f = i.cant / 100;
                nut.p += info.pro * f; nut.c += info.car * f; nut.g += info.gra * f;
            });
            const cal = (nut.p*4) + (nut.c*4) + (nut.g*9);

            const recData = {
                id: editId || Date.now(),
                titulo: t, desc: document.getElementById('r-desc').value,
                utensilios: [...tempUtensilios], pasos: [...tempPasos], ingredientes: [...tempIngredientes],
                nut: { ...nut, cal }
            };

            if(editId) {
                const idx = RECETAS.findIndex(r => r.id === editId);
                RECETAS[idx] = recData;
                showToast("Receta actualizada");
            } else {
                RECETAS.push(recData);
                showToast("Receta creada");
            }

            editId = null;
            document.getElementById('form-title').innerText = "Nueva Receta";
            document.getElementById('btn-cancel-edit').style.display = 'none';
            guardarEnLocalStorage(); renderRecetas(); resetForm();
            switchTab('tab-view', document.getElementById('btn-view'));
        }

        function renderRecetas() {
            const cont = document.getElementById('recipe-list');
            cont.innerHTML = RECETAS.map(r => `
                <div class="card">
                    <div style="display:flex; justify-content:space-between; align-items:start;">
                        <div>
                            <h2 style="margin:0; color:var(--p);">${r.titulo}</h2>
                            <p style="font-size:14px; color:#666;">${r.desc}</p>
                        </div>
                        <div>
                            <button class="btn btn-p" onclick="editarReceta(${r.id})">Editar</button>
                            <button class="btn btn-d" onclick="eliminarReceta(${r.id})">Borrar</button>
                        </div>
                    </div>
                    
                    <div style="margin:15px 0;">
                        <span class="macro-badge" style="background:#e74c3c">🔥 ${r.nut.cal.toFixed(0)} kcal</span>
                        <span class="macro-badge" style="background:#2ecc71">💪 ${r.nut.p.toFixed(1)}g P</span>
                        <span class="macro-badge" style="background:#3498db">🍞 ${r.nut.c.toFixed(1)}g C</span>
                    </div>

                    <div class="recipe-detail">
                        <div>
                            <b>Ingredientes:</b>
                            <ul>${r.ingredientes.map(i => `<li>${i.nombre} (${i.cant}g)</li>`).join("")}</ul>
                            <b>Utensilios:</b>
                            <ul>${r.utensilios.map(u => `<li>${u}</li>`).join("")}</ul>
                        </div>
                        <div>
                            <b>Preparación:</b>
                            <ol>${r.pasos.map(p => `<li>${p}</li>`).join("")}</ol>
                        </div>
                    </div>
                </div>
            `).join("");
        }

        function eliminarReceta(id) {
            if(confirm("¿Eliminar receta?")) {
                RECETAS = RECETAS.filter(r => r.id !== id);
                guardarEnLocalStorage(); renderRecetas();
                showToast("Receta eliminada");
            }
        }

        function descargarXML() {
            let xml = '<?xml version="1.0" encoding="UTF-8"?>\n<?xml-stylesheet type="text/xsl" href="estilo.xsl"?>\n<recetario>\n';
            xml += '  <base_ingredientes>\n';
            for(let n in DB_INGREDIENTES) {
                let i = DB_INGREDIENTES[n];
                xml += `    <ingrediente_db nombre="${n}"><calorias>${i.cal}</calorias><proteinas>${i.pro}</proteinas><carbohidratos>${i.car}</carbohidratos><grasas>${i.gra}</grasas></ingrediente_db>\n`;
            }
            xml += '  </base_ingredientes>\n  <recetas>\n';
            RECETAS.forEach(r => {
                xml += `    <receta>\n      <titulo>${r.titulo}</titulo><descripcion>${r.desc}</descripcion>\n`;
                xml += `      <nutricion><calorias>${r.nut.cal.toFixed(1)}</calorias><proteinas>${r.nut.p.toFixed(1)}</proteinas><carbohidratos>${r.nut.c.toFixed(1)}</carbohidratos><grasas>${r.nut.g.toFixed(1)}</grasas></nutricion>\n`;
                xml += `      <ingredientes>${r.ingredientes.map(i => `<ingrediente cantidad="${i.cant}g">${i.nombre}</ingrediente>`).join("")}</ingredientes>\n`;
                xml += `      <utensilios>${r.utensilios.map(u => `<utensilio>${u}</utensilio>`).join("")}</utensilios>\n`;
                xml += `      <pasos>${r.pasos.map(p => `<paso>${p}</paso>`).join("")}</pasos>\n    </receta>\n`;
            });
            xml += '  </recetas>\n</recetario>';
            const b = new Blob([xml], {type: 'text/xml'});
            const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'recetas.xml'; a.click();
        }

        function actualizarSelects() {
            const s = document.getElementById('r-ing-select');
            s.innerHTML = Object.keys(DB_INGREDIENTES).sort().map(n => `<option value="${n}">${n}</option>`).join("");
        }

        function guardarEnLocalStorage() {
            localStorage.setItem('nutri_v4_db', JSON.stringify(DB_INGREDIENTES));
            localStorage.setItem('nutri_v4_recs', JSON.stringify(RECETAS));
        }

        function cargarDeLocalStorage() {
            const d = localStorage.getItem('nutri_v4_db'); const r = localStorage.getItem('nutri_v4_recs');
            if(d) DB_INGREDIENTES = JSON.parse(d); if(r) RECETAS = JSON.parse(r);
        }
        
        function importarXML(input) {
            const file = input.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const parser = new DOMParser();
                    const xmlDoc = parser.parseFromString(e.target.result, "text/xml");

                    // 1. Limpiar datos actuales
                    DB_INGREDIENTES = {};
                    RECETAS = [];

                    // 2. Procesar Base de Ingredientes
                    const ingNodes = xmlDoc.querySelectorAll('ingrediente_db');
                    ingNodes.forEach(node => {
                        const nombre = node.getAttribute('nombre');
                        DB_INGREDIENTES[nombre] = {
                            cal: parseFloat(node.querySelector('calorias').textContent),
                            pro: parseFloat(node.querySelector('proteinas').textContent),
                            car: parseFloat(node.querySelector('carbohidratos').textContent),
                            gra: parseFloat(node.querySelector('grasas').textContent)
                        };
                    });

                    // 3. Procesar Recetas
                    const recNodes = xmlDoc.querySelectorAll('receta');
                    recNodes.forEach(node => {
                        const ingredientes = [];
                        node.querySelectorAll('ingrediente').forEach(i => {
                            ingredientes.push({
                                nombre: i.textContent,
                                cant: parseFloat(i.getAttribute('cantidad'))
                            });
                        });

                        RECETAS.push({
                            id: Date.now() + Math.random(), // ID único temporal
                            titulo: node.querySelector('titulo').textContent,
                            desc: node.querySelector('descripcion').textContent,
                            nut: {
                                cal: parseFloat(node.querySelector('nutricion calorias').textContent),
                                p: parseFloat(node.querySelector('nutricion proteinas').textContent),
                                c: parseFloat(node.querySelector('nutricion carbohidratos').textContent),
                                g: parseFloat(node.querySelector('nutricion grasas').textContent)
                            },
                            ingredientes: ingredientes,
                            utensilios: Array.from(node.querySelectorAll('utensilio')).map(u => u.textContent),
                            pasos: Array.from(node.querySelectorAll('paso')).map(p => p.textContent)
                        });
                    });

                    // 4. Guardar y refrescar
                    guardarEnLocalStorage();
                    actualizarSelects();
                    renderRecetas();
                    renderDB();
                    showToast("XML importado con éxito");
                    
                } catch (error) {
                    console.error(error);
                    alert("Error al procesar el XML. Asegúrate de que el formato sea correcto.");
                }
            };
            reader.readAsText(file);
        }
    //]]>
    </script>
</body>
</html>
</xsl:template>
</xsl:stylesheet>