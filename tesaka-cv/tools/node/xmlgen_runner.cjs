#!/usr/bin/env node
/**
 * Runner CommonJS para facturacionelectronicapy-xmlgen
 * 
 * Uso:
 *   node xmlgen_runner.cjs --params params.json --data data.json [--options options.json]
 * 
 * Escribe el XML generado a stdout.
 */
const fs = require('fs');
const path = require('path');

// Parsear argumentos
const args = process.argv.slice(2);
let paramsPath = null;
let dataPath = null;
let optionsPath = null;
let outPath = null;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--params' && args[i + 1]) {
    paramsPath = path.resolve(args[i + 1]);
    i++;
  } else if (args[i] === '--data' && args[i + 1]) {
    dataPath = path.resolve(args[i + 1]);
    i++;
  } else if (args[i] === '--options' && args[i + 1]) {
    optionsPath = path.resolve(args[i + 1]);
    i++;
  } else if (args[i] === '--out' && args[i + 1]) {
    outPath = path.resolve(args[i + 1]);
    i++;
  }
}

// Validar argumentos requeridos
if (!paramsPath || !dataPath) {
  console.error('❌ Error: Se requieren --params y --data');
  console.error('   Uso: node xmlgen_runner.cjs --params <json> --data <json> [--options <json>]');
  process.exit(1);
}

// Leer archivos JSON
let params, data, options = {};

try {
  params = JSON.parse(fs.readFileSync(paramsPath, 'utf-8'));
} catch (error) {
  console.error(`❌ Error al leer params.json: ${error.message}`);
  process.exit(1);
}

try {
  data = JSON.parse(fs.readFileSync(dataPath, 'utf-8'));
} catch (error) {
  console.error(`❌ Error al leer data.json: ${error.message}`);
  process.exit(1);
}

if (optionsPath) {
  try {
    options = JSON.parse(fs.readFileSync(optionsPath, 'utf-8'));
  } catch (error) {
    console.error(`❌ Error al leer options.json: ${error.message}`);
    process.exit(1);
  }
}

// Cargar módulo xmlgen
let xmlgen;
try {
  const mod = require('facturacionelectronicapy-xmlgen');
  
  // Manejar diferentes formas de export según README:
  // - module.exports = { generateXMLDE }
  // - export default { generateXMLDE }
  // - o anidado (mod.generateXMLDE / mod.default.generateXMLDE)
  
  // Estrategia 1: mod.generateXMLDE existe directamente
  if (mod && typeof mod.generateXMLDE === 'function') {
    xmlgen = mod;
  } 
  // Estrategia 2: mod.default.generateXMLDE
  else if (mod.default && typeof mod.default.generateXMLDE === 'function') {
    xmlgen = mod.default;
  }
  // Estrategia 3: mod.default es un objeto que puede tener generateXMLDE
  else if (mod.default && typeof mod.default === 'object' && mod.default.generateXMLDE) {
    xmlgen = mod.default;
  }
  // Estrategia 4: mod es la función directamente (poco común)
  else if (typeof mod === 'function') {
    xmlgen = mod;
  }
  // Estrategia 5: Buscar en propiedades del módulo
  else if (mod && typeof mod === 'object') {
    // Intentar encontrar generateXMLDE en cualquier nivel
    if (mod.generateXMLDE) {
      xmlgen = mod;
    } else if (mod.default && mod.default.generateXMLDE) {
      xmlgen = mod.default;
    } else {
      xmlgen = mod;
    }
  }
  // Fallback: usar el módulo tal cual
  else {
    xmlgen = mod;
  }
} catch (error) {
  console.error('❌ Error al cargar facturacionelectronicapy-xmlgen:');
  console.error(`   ${error.message}`);
  console.error('   Ejecuta: cd tesaka-cv/tools/node && npm install');
  process.exit(1);
}

// Validar que existe generateXMLDE
if (!xmlgen || typeof xmlgen.generateXMLDE !== 'function') {
  const availableKeys = xmlgen ? Object.keys(xmlgen).join(', ') : 'none';
  console.error('❌ Error: generateXMLDE no está disponible');
  console.error(`   Keys disponibles en xmlgen: ${availableKeys}`);
  if (xmlgen && xmlgen.default) {
    const defaultKeys = Object.keys(xmlgen.default).join(', ');
    console.error(`   Keys en xmlgen.default: ${defaultKeys}`);
  }
  console.error('   El módulo puede no estar instalado correctamente o la versión es incompatible');
  console.error('   Revisa el README de facturacionelectronicapy-xmlgen para la forma correcta de importar');
  process.exit(2);
}

// Generar XML
try {
  const xml = xmlgen.generateXMLDE(params, data, options);
  
  if (!xml) {
    console.error('❌ Error: generateXMLDE no retornó XML');
    process.exit(1);
  }
  
  // Si se especificó --out, escribir al archivo; si no, a stdout (solo XML, sin logs)
  if (outPath) {
    fs.writeFileSync(outPath, typeof xml === 'string' ? xml : JSON.stringify(xml, null, 2), 'utf-8');
  } else {
    // Escribir a stdout (solo XML, sin logs)
    process.stdout.write(typeof xml === 'string' ? xml : JSON.stringify(xml, null, 2));
  }
  
} catch (error) {
  // Errores van a stderr para no contaminar stdout si se redirige
  console.error('❌ Error al generar XML:');
  console.error(`   ${error.message}`);
  if (error.stack) {
    // Mostrar solo las primeras líneas del stack para no saturar
    const stackLines = error.stack.split('\n').slice(0, 10);
    console.error(`   Stack (primeras 10 líneas):\n${stackLines.map(l => '   ' + l).join('\n')}`);
  }
  
  // Si el error menciona establecimientos o actividadesEconomicas, dar pista útil
  if (error.message && (
    error.message.includes('establecimientos') ||
    error.message.includes('actividadesEconomicas') ||
    error.message.includes('establecimiento')
  )) {
    console.error('');
    console.error('   💡 Pista: Asegúrate de que params tenga:');
    console.error('      - params.establecimientos: array con objetos {codigo, denominacion, ciudad, distrito, departamento}');
    console.error('      - params.actividadesEconomicas: array no vacío de códigos');
    console.error('      - data.establecimiento: string que coincida con params.establecimientos[].codigo');
  }
  
  process.exit(1);
}

