#!/usr/bin/env node
/**
 * Wrapper Node.js para generar DE usando facturacionelectronicapy-xmlgen
 * 
 * Uso:
 *   node generate_de.js <input_json_path> <output_xml_path>
 * 
 * Lee un JSON de entrada (formato de_input.json) y genera un XML DE.
 */
const fs = require('fs');
const path = require('path');

// Cargar la librería xmlgen
let xmlgen;
try {
  xmlgen = require('facturacionelectronicapy-xmlgen');
} catch (error) {
  console.error('❌ Error: facturacionelectronicapy-xmlgen no está instalado.');
  console.error('   Ejecuta: npm install');
  console.error('   Error detallado:', error.message);
  process.exit(1);
}

// Argumentos de línea de comandos
const args = process.argv.slice(2);

if (args.length < 1) {
  console.error('❌ Uso: node generate_de.js <input_json_path> [output_xml_path]');
  process.exit(1);
}

const inputJsonPath = path.resolve(args[0]);
const outputXmlPath = args[1] ? path.resolve(args[1]) : null;

// Leer JSON de entrada
let inputData;
try {
  const inputContent = fs.readFileSync(inputJsonPath, 'utf-8');
  inputData = JSON.parse(inputContent);
} catch (error) {
  console.error(`❌ Error al leer JSON de entrada: ${inputJsonPath}`);
  console.error('   Error:', error.message);
  process.exit(1);
}

// Validar estructura mínima
if (!inputData.buyer || !inputData.transaction || !inputData.items) {
  console.error('❌ JSON de entrada inválido. Requiere: buyer, transaction, items');
  process.exit(1);
}

try {
  // Mapear formato de_input.json al formato esperado por xmlgen
  // Nota: El formato exacto depende de la API de xmlgen
  // Aquí asumimos una estructura similar a la documentación
  
  // Generar XML usando xmlgen
  // La API exacta puede variar, ajustar según documentación del repo
  let xmlContent;
  
  // Intentar diferentes formas de invocación según la API de xmlgen
  if (typeof xmlgen.generateDE === 'function') {
    xmlContent = xmlgen.generateDE(inputData);
  } else if (typeof xmlgen.generate === 'function') {
    xmlContent = xmlgen.generate(inputData);
  } else if (typeof xmlgen === 'function') {
    xmlContent = xmlgen(inputData);
  } else if (xmlgen.default && typeof xmlgen.default === 'function') {
    xmlContent = xmlgen.default(inputData);
  } else {
    // Intentar acceder a métodos comunes
    const methods = Object.keys(xmlgen);
    console.error('❌ No se pudo encontrar método de generación en xmlgen');
    console.error(`   Métodos disponibles: ${methods.join(', ')}`);
    console.error('   Revisa la documentación de facturacionelectronicapy-xmlgen');
    process.exit(1);
  }
  
  if (!xmlContent) {
    console.error('❌ xmlgen no retornó contenido XML');
    process.exit(1);
  }
  
  // Asegurar que es string
  if (typeof xmlContent !== 'string') {
    xmlContent = String(xmlContent);
  }
  
  // Escribir archivo de salida
  if (outputXmlPath) {
    fs.writeFileSync(outputXmlPath, xmlContent, 'utf-8');
    console.log(`✅ XML generado: ${outputXmlPath}`);
  } else {
    // Escribir a stdout
    console.log(xmlContent);
  }
  
} catch (error) {
  console.error('❌ Error al generar XML:');
  console.error('   ', error.message);
  if (error.stack) {
    console.error('   Stack:', error.stack);
  }
  process.exit(1);
}

