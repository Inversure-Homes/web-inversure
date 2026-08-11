/* Compra de participaciones. JS plano, sin dependencias, como landing.js. */
(function () {
  "use strict";

  var datos = document.getElementById("sorteo-datos");
  var form = document.getElementById("sorteo-form");
  if (!datos || !form) return;

  var cfg = JSON.parse(datos.textContent);
  var BLOQUE = 100;

  var ocupadas = new Map();
  cfg.ocupadas.forEach(function (o) {
    ocupadas.set(o.n, o.e);
  });

  var estado = {
    modo: "rapida",
    cantidad: 1,
    elegidos: [],
    bloque: 0,
    enviando: false,
  };

  var el = {
    pestanas: form.querySelectorAll(".sorteo-pestanas button"),
    paneles: form.querySelectorAll("[data-panel]"),
    atajos: form.querySelectorAll("[data-cantidad]"),
    cantidad: document.getElementById("sorteo-cantidad"),
    rejilla: document.getElementById("sorteo-rejilla"),
    bloque: document.getElementById("sorteo-bloque"),
    rango: document.getElementById("sorteo-rango"),
    busqueda: document.getElementById("sorteo-busqueda"),
    buscar: document.getElementById("sorteo-buscar"),
    elegidos: document.getElementById("sorteo-elegidos"),
    resumen: document.getElementById("sorteo-resumen-texto"),
    total: document.getElementById("sorteo-total"),
    acepta: document.getElementById("sorteo-acepta"),
    error: document.getElementById("sorteo-error"),
    enviar: document.getElementById("sorteo-enviar"),
  };

  var moneda = new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
  });

  function precio() {
    return parseFloat(cfg.precio);
  }

  function cuantas() {
    return estado.modo === "rapida" ? estado.cantidad : estado.elegidos.length;
  }

  function mostrarError(mensaje) {
    if (!mensaje) {
      el.error.hidden = true;
      el.error.textContent = "";
      return;
    }
    el.error.hidden = false;
    el.error.textContent = mensaje;
  }

  // -- Rejilla ------------------------------------------------------------

  function pintarBloques() {
    var total = Math.ceil(cfg.total / BLOQUE);
    var html = "";
    for (var i = 0; i < total; i++) {
      var desde = i * BLOQUE + 1;
      var hasta = Math.min((i + 1) * BLOQUE, cfg.total);
      html += '<option value="' + i + '">' + desde + " – " + hasta + "</option>";
    }
    el.bloque.innerHTML = html;
  }

  function pintarRejilla() {
    var desde = estado.bloque * BLOQUE + 1;
    var hasta = Math.min(desde + BLOQUE - 1, cfg.total);
    el.rango.textContent =
      "Mostrando del " + desde + " al " + hasta + " de " + cfg.total +
      ". Los tachados ya están vendidos.";

    var trozos = [];
    for (var n = desde; n <= hasta; n++) {
      var ocupada = ocupadas.get(n);
      var visual = estado.elegidos.indexOf(n) !== -1 ? "elegido" : ocupada || "libre";
      trozos.push(
        '<button type="button" class="sorteo-boleto" data-numero="' + n +
          '" data-estado="' + visual + '"' +
          (ocupada ? " disabled" : "") +
          ' aria-label="Número ' + n + (ocupada ? " (no disponible)" : "") + '">' +
          n +
          "</button>"
      );
    }
    el.rejilla.innerHTML = trozos.join("");
    el.bloque.value = String(estado.bloque);
  }

  function pintarElegidos() {
    if (!estado.elegidos.length) {
      el.elegidos.hidden = true;
      el.elegidos.innerHTML = "";
      return;
    }
    el.elegidos.hidden = false;
    el.elegidos.innerHTML = estado.elegidos
      .map(function (n) {
        return (
          '<button type="button" class="sorteo-chip activo" data-quitar="' + n +
          '" aria-label="Quitar el número ' + n + '">' + n + " ✕</button>"
        );
      })
      .join("");
  }

  function alternar(n) {
    mostrarError("");
    var i = estado.elegidos.indexOf(n);
    if (i !== -1) {
      estado.elegidos.splice(i, 1);
    } else {
      if (estado.elegidos.length >= cfg.maximo) {
        mostrarError("Máximo " + cfg.maximo + " participaciones por pedido.");
        return;
      }
      estado.elegidos.push(n);
      estado.elegidos.sort(function (a, b) {
        return a - b;
      });
    }
    pintarRejilla();
    pintarElegidos();
    refrescar();
  }

  // -- Resumen ------------------------------------------------------------

  function refrescar() {
    var n = cuantas();
    if (estado.modo === "rapida") {
      el.resumen.textContent =
        estado.cantidad + (estado.cantidad === 1
          ? " participación al azar"
          : " participaciones al azar");
    } else {
      el.resumen.textContent = estado.elegidos.length
        ? "Números " + estado.elegidos.join(", ")
        : "Ningún número seleccionado";
    }
    el.total.textContent = moneda.format(n * precio());
    el.enviar.disabled = !n || !el.acepta.checked || estado.enviando;
  }

  // -- Eventos ------------------------------------------------------------

  el.pestanas.forEach(function (boton) {
    boton.addEventListener("click", function () {
      estado.modo = boton.dataset.modo;
      el.pestanas.forEach(function (b) {
        b.classList.toggle("activa", b === boton);
      });
      el.paneles.forEach(function (p) {
        p.hidden = p.dataset.panel !== estado.modo;
      });
      refrescar();
    });
  });

  el.atajos.forEach(function (boton) {
    boton.addEventListener("click", function () {
      estado.cantidad = parseInt(boton.dataset.cantidad, 10);
      el.cantidad.value = estado.cantidad;
      el.atajos.forEach(function (b) {
        b.classList.toggle("activo", b === boton);
      });
      refrescar();
    });
  });

  el.cantidad.addEventListener("input", function () {
    var v = parseInt(el.cantidad.value, 10) || 1;
    estado.cantidad = Math.max(1, Math.min(cfg.maximo, v));
    el.atajos.forEach(function (b) {
      b.classList.toggle(
        "activo",
        parseInt(b.dataset.cantidad, 10) === estado.cantidad
      );
    });
    refrescar();
  });

  el.rejilla.addEventListener("click", function (e) {
    var boton = e.target.closest("[data-numero]");
    if (boton && !boton.disabled) alternar(parseInt(boton.dataset.numero, 10));
  });

  el.elegidos.addEventListener("click", function (e) {
    var boton = e.target.closest("[data-quitar]");
    if (boton) alternar(parseInt(boton.dataset.quitar, 10));
  });

  el.bloque.addEventListener("change", function () {
    estado.bloque = parseInt(el.bloque.value, 10);
    pintarRejilla();
  });

  el.buscar.addEventListener("click", function () {
    var n = parseInt(el.busqueda.value, 10);
    if (!n || n < 1 || n > cfg.total) {
      mostrarError("Introduce un número entre 1 y " + cfg.total + ".");
      return;
    }
    mostrarError("");
    estado.bloque = Math.floor((n - 1) / BLOQUE);
    if (!ocupadas.has(n)) {
      alternar(n);
    } else {
      pintarRejilla();
    }
  });

  el.busqueda.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      el.buscar.click();
    }
  });

  el.acepta.addEventListener("change", refrescar);

  // -- Disponibilidad en vivo ---------------------------------------------

  function sincronizar(lista) {
    ocupadas = new Map();
    lista.forEach(function (o) {
      ocupadas.set(o.n, o.e);
    });
    estado.elegidos = estado.elegidos.filter(function (n) {
      return !ocupadas.has(n);
    });
    pintarRejilla();
    pintarElegidos();
    refrescar();
  }

  // Otra persona puede comprar mientras miras la página.
  setInterval(function () {
    fetch("/sorteo/estado/", { headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (d) {
        if (d) sincronizar(d.ocupadas);
      })
      .catch(function () {
        /* sin conexión: se reintenta al siguiente ciclo */
      });
  }, 15000);

  // -- Envío ---------------------------------------------------------------

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (estado.enviando) return;

    mostrarError("");
    estado.enviando = true;
    el.enviar.disabled = true;
    el.enviar.textContent = "Procesando…";

    var cuerpo = {
      nombre: document.getElementById("sorteo-nombre").value,
      email: document.getElementById("sorteo-email").value,
      telefono: document.getElementById("sorteo-telefono").value,
      acepta_bases: el.acepta.checked,
      mayor_edad: el.acepta.checked,
    };
    if (estado.modo === "rapida") {
      cuerpo.cantidad = estado.cantidad;
    } else {
      cuerpo.numeros = estado.elegidos;
    }

    fetch("/sorteo/reservar/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value,
      },
      body: JSON.stringify(cuerpo),
    })
      .then(function (r) {
        return r.json().then(function (d) {
          return { ok: r.ok, datos: d };
        });
      })
      .then(function (res) {
        if (!res.ok) {
          mostrarError(res.datos.error || "No se pudo completar la reserva.");
          if (res.datos.ocupadas) sincronizar(res.datos.ocupadas);
          return;
        }
        window.location.href = res.datos.url;
      })
      .catch(function () {
        mostrarError("Error de red. Inténtalo de nuevo.");
      })
      .finally(function () {
        estado.enviando = false;
        el.enviar.textContent = "Ir al pago";
        refrescar();
      });
  });

  pintarBloques();
  pintarRejilla();
  refrescar();
})();
