// @ts-check
import {themes as prismThemes} from 'prism-react-renderer';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'RutaViva Mobility',
  tagline: 'Plataforma de Datos, Telemetría y Tarifas Dinámicas',
  favicon: 'img/favicon.ico',

  url: 'https://rutaviva.mobility.internal',
  baseUrl: '/',

  organizationName: 'rutaviva',
  projectName: 'rutaviva-docs',

  onBrokenLinks: 'warn',

  i18n: {
    defaultLocale: 'es',
    locales: ['es'],
  },

  markdown: {
    mermaid: true,
  },
  themes: ['@docusaurus/theme-mermaid'],

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: './sidebars.js',
          routeBasePath: '/', // Hace que docs sea la raíz
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      navbar: {
        title: 'RutaViva Mobility',
        logo: {
          alt: 'RutaViva Logo',
          src: 'img/logo.svg',
        },
        items: [
          {
            type: 'docSidebar',
            sidebarId: 'docsSidebar',
            position: 'left',
            label: 'Documentación Técnica',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'Docs',
            items: [
              {
                label: 'Visión General',
                to: '/',
              },
              {
                label: 'Arquitectura',
                to: '/arquitectura/vision-general',
              },
              {
                label: 'Módulos',
                to: '/modulos/resumen',
              },
            ],
          },
          {
            title: 'Proyecto',
            items: [
              {
                label: 'RutaViva Movilidad Inc.',
                href: 'https://github.com',
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} RutaViva Mobility Inc. Documentación Técnica del Sistema.`,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
        additionalLanguages: ['python', 'bash', 'json', 'sql'],
      },
    }),
};

export default config;
