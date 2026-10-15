// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docsSidebar: [
    {
      type: 'doc',
      id: 'index',
      label: '🚀 Inicio & Visión General',
    },
    {
      type: 'category',
      label: '🏛 Arquitectura del Sistema',
      collapsed: false,
      items: [
        'arquitectura/vision-general',
        'arquitectura/pipeline-end-to-end',
        'arquitectura/adrs',
        'arquitectura/puntos-abiertos-tensiones',
      ],
    },
    {
      type: 'category',
      label: '🗄️ Modelo y Datos',
      collapsed: false,
      items: [
        'datos/modelo-operacional-mer',
        'datos/modelo-analitico-gold',
        'datos/correspondencia-modelos',
        'datos/estandares-glosario',
      ],
    },
    {
      type: 'category',
      label: '🧩 Módulos y Microservicios',
      collapsed: false,
      items: [
        'modulos/resumen',
        'modulos/infraestructura',
        'modulos/seed-cli',
        'modulos/telemetry-simulator',
        'modulos/multiplier-api',
        'modulos/pressure-worker',
        'modulos/request-simulator',
        'modulos/batch-spark-airflow',
      ],
    },
    {
      type: 'category',
      label: '⚖️ Reglas de Negocio & Auditoría',
      collapsed: false,
      items: [
        'reglas-negocio/reglas-tarifarias',
        'reglas-negocio/auditoria-trazabilidad',
      ],
    },
    {
      type: 'category',
      label: '🛠️ Guías & Sprint Roadmap',
      collapsed: false,
      items: [
        'guias/puesta-en-marcha',
        'guias/sprints-roadmap',
      ],
    },
  ],
};

export default sidebars;
