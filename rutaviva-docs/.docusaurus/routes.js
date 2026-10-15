import React from 'react';
import ComponentCreator from '@docusaurus/ComponentCreator';

export default [
  {
    path: '/__docusaurus/debug',
    component: ComponentCreator('/__docusaurus/debug', '5ff'),
    exact: true
  },
  {
    path: '/__docusaurus/debug/config',
    component: ComponentCreator('/__docusaurus/debug/config', '5ba'),
    exact: true
  },
  {
    path: '/__docusaurus/debug/content',
    component: ComponentCreator('/__docusaurus/debug/content', 'a2b'),
    exact: true
  },
  {
    path: '/__docusaurus/debug/globalData',
    component: ComponentCreator('/__docusaurus/debug/globalData', 'c3c'),
    exact: true
  },
  {
    path: '/__docusaurus/debug/metadata',
    component: ComponentCreator('/__docusaurus/debug/metadata', '156'),
    exact: true
  },
  {
    path: '/__docusaurus/debug/registry',
    component: ComponentCreator('/__docusaurus/debug/registry', '88c'),
    exact: true
  },
  {
    path: '/__docusaurus/debug/routes',
    component: ComponentCreator('/__docusaurus/debug/routes', '000'),
    exact: true
  },
  {
    path: '/blog',
    component: ComponentCreator('/blog', '98b'),
    exact: true
  },
  {
    path: '/markdown-page',
    component: ComponentCreator('/markdown-page', '53a'),
    exact: true
  },
  {
    path: '/docs',
    component: ComponentCreator('/docs', 'ccd'),
    routes: [
      {
        path: '/docs',
        component: ComponentCreator('/docs', 'e13'),
        routes: [
          {
            path: '/docs',
            component: ComponentCreator('/docs', 'e55'),
            routes: [
              {
                path: '/docs/',
                component: ComponentCreator('/docs/', '4a8'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/arquitectura/adrs',
                component: ComponentCreator('/docs/arquitectura/adrs', 'b54'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/arquitectura/pipeline-end-to-end',
                component: ComponentCreator('/docs/arquitectura/pipeline-end-to-end', '364'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/arquitectura/puntos-abiertos-tensiones',
                component: ComponentCreator('/docs/arquitectura/puntos-abiertos-tensiones', '4e1'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/arquitectura/vision-general',
                component: ComponentCreator('/docs/arquitectura/vision-general', 'b86'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/datos/correspondencia-modelos',
                component: ComponentCreator('/docs/datos/correspondencia-modelos', '69e'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/datos/estandares-glosario',
                component: ComponentCreator('/docs/datos/estandares-glosario', 'b5a'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/datos/modelo-analitico-gold',
                component: ComponentCreator('/docs/datos/modelo-analitico-gold', 'eaf'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/datos/modelo-operacional-mer',
                component: ComponentCreator('/docs/datos/modelo-operacional-mer', 'b85'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/guias/puesta-en-marcha',
                component: ComponentCreator('/docs/guias/puesta-en-marcha', '5ea'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/guias/sprints-roadmap',
                component: ComponentCreator('/docs/guias/sprints-roadmap', 'de3'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/modulos/batch-spark-airflow',
                component: ComponentCreator('/docs/modulos/batch-spark-airflow', '151'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/modulos/infraestructura',
                component: ComponentCreator('/docs/modulos/infraestructura', '117'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/modulos/multiplier-api',
                component: ComponentCreator('/docs/modulos/multiplier-api', 'b55'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/modulos/pressure-worker',
                component: ComponentCreator('/docs/modulos/pressure-worker', 'a87'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/modulos/request-simulator',
                component: ComponentCreator('/docs/modulos/request-simulator', 'b2d'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/modulos/resumen',
                component: ComponentCreator('/docs/modulos/resumen', '5b5'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/modulos/seed-cli',
                component: ComponentCreator('/docs/modulos/seed-cli', 'b03'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/modulos/telemetry-simulator',
                component: ComponentCreator('/docs/modulos/telemetry-simulator', '664'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/reglas-negocio/auditoria-trazabilidad',
                component: ComponentCreator('/docs/reglas-negocio/auditoria-trazabilidad', '742'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/docs/reglas-negocio/reglas-tarifarias',
                component: ComponentCreator('/docs/reglas-negocio/reglas-tarifarias', 'fc1'),
                exact: true,
                sidebar: "tutorialSidebar"
              }
            ]
          }
        ]
      }
    ]
  },
  {
    path: '/',
    component: ComponentCreator('/', '2e1'),
    exact: true
  },
  {
    path: '*',
    component: ComponentCreator('*'),
  },
];
