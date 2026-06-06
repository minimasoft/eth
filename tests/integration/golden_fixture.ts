/**
 * Golden test fixture for v6.0 integration tests.
 *
 * A crafted Spanish legal text (reclamación de cantidad) designed to
 * reliably produce:
 * - 2 events with clear date boundaries
 * - 3 person entities (Laura Fernández, Miguel Ángel Torres, Antonio Ruiz)
 * - 1 place entity (Barcelona)
 * - element_field-tagged references for tiempo, humanos, espacio, objetos
 *
 * @module
 */

export const GOLDEN_FIXTURE = [
  "JUZGADO DE PRIMERA INSTANCIA NÚMERO 3",
  "BARCELONA",
  "",
  "JUICIO VERBAL NÚMERO 456/2024",
  "RECLAMACIÓN DE CANTIDAD",
  "",
  "PRIMERO. — El día 15 de enero de 2024, a las 10:00 horas,",
  "en el domicilio de la Avenida Diagonal número 200,",
  "08013 Barcelona, la Sra. Laura Fernández, mayor de edad,",
  "con DNI 12.345.678, presentó una demanda de reclamación",
  "de cantidad contra el Sr. Miguel Ángel Torres, mayor de",
  "edad, con DNI 98.765.432, por impago de honorarios",
  "profesionales derivados de servicios de asesoría jurídica.",
  "",
  "La demanda fue presentada ante el Juzgado Decano de",
  "Barcelona y turnada al Juzgado de Primera Instancia",
  "Número 3, sito en la Vía Laietana número 50.",
  "En su escrito inicial, la Sra. Fernández solicitó",
  "la condena del demandado al pago de 8.000 euros más",
  "los intereses legales desde la fecha de la reclamación",
  "extrajudicial realizada el día 1 de diciembre de 2023.",
  "",
  "SEGUNDO. — El día 28 de febrero de 2024, el Juzgado",
  "celebró la vista oral en la Sala de Vistas sita en la",
  "Calle Pau Claris número 100, 08010 Barcelona, donde",
  "compareció la parte demandante, la Sra. Laura Fernández,",
  "asistida por el letrado Don Antonio Ruiz, colegiado del",
  "Ilustre Colegio de la Abogacía de Barcelona, y la parte",
  "demandada, el Sr. Miguel Ángel Torres, quien no",
  "compareció pese a estar citado en legal forma.",
  "",
  "TERCERO. — En el acto de la vista, la Sra. Fernández",
  "ratificó íntegramente su demanda y solicitó el recibimiento",
  "del pleito a prueba. Aportó como documentos: el contrato",
  "de prestación de servicios profesionales de fecha 1 de",
  "septiembre de 2023, las facturas impagadas números 001",
  "a 005 por importe total de 8.000 euros, y el burofax de",
  "reclamación extrajudicial remitido el 1 de diciembre de 2023.",
  "El letrado Don Antonio Ruiz solicitó igualmente la",
  "imposición de costas a la parte demandada por su temeridad.",
  "",
  "CUARTO. — La parte demandada, el Sr. Miguel Ángel Torres,",
  "no presentó escrito de contestación a la demanda ni",
  "compareció al acto de la vista, por lo que fue declarado",
  "en situación de rebeldía procesal conforme al artículo",
  "496 de la Ley de Enjuiciamiento Civil.",
  "",
].join("\n");
