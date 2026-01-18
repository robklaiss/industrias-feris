const fs = require("fs");
const path = require("path");
const setApi = require("facturacionelectronicapy-setapi").default;

async function main() {
  const xmlPath = process.argv[2];
  if (!xmlPath) {
    console.error("Uso: node send_with_tips_setapi.js /path/al/rde_signed.xml");
    process.exit(1);
  }

  const xmlSigned = fs.readFileSync(xmlPath, "utf8");

  const env = "test";
  const id = String(Date.now());

  const certPath = process.env.SIFEN_CERT_PATH;
  const certPass =
    process.env.SIFEN_CERT_PASS ||
    process.env.SIFEN_P12_PASS ||
    process.env.SIFEN_CERT_PASSWORD;

  if (!certPath || !certPass) {
    console.error("Faltan env vars: SIFEN_CERT_PATH y SIFEN_CERT_PASS (password del .p12)");
    process.exit(1);
  }

  const resp = await setApi.recibeLote(id, [xmlSigned], env, certPath, certPass);

  // Guardar SIEMPRE como JSON por si resp es objeto
  const outJson = path.join(process.cwd(), `tips_recibeLote_response_${id}.json`);
  fs.writeFileSync(outJson, JSON.stringify(resp, null, 2), "utf8");
  console.log("OK. Respuesta (JSON) guardada en:", outJson);

  // Si también hay un XML dentro, lo guardamos aparte
  const maybeXml =
    (typeof resp === "string" && resp) ||
    resp?.rawXml ||
    resp?.xml ||
    resp?.response ||
    resp?.data;

  if (typeof maybeXml === "string" && maybeXml.trim().startsWith("<")) {
    const outXml = path.join(process.cwd(), `tips_recibeLote_response_${id}.xml`);
    fs.writeFileSync(outXml, maybeXml, "utf8");
    console.log("OK. Respuesta (XML) guardada en:", outXml);
  }
}

main().catch((e) => {
  console.error("ERROR:", e && e.stack ? e.stack : e);
  process.exit(1);
});