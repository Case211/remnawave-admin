import type { DefaultTheme, LocaleSpecificConfig } from 'vitepress'

export const en: LocaleSpecificConfig<DefaultTheme.Config> = {
  lang: 'en-US',
  description: 'Telegram bot and web panel for Remnawave: anti-abuse, nodes, mail, monitoring',
  themeConfig: {
    nav: [
      { text: 'Guide', link: '/en/guide/overview', activeMatch: '/en/guide/' },
      { text: 'Reference', link: '/en/reference/env', activeMatch: '/en/reference/' },
      {
        text: 'Links',
        items: [
          { text: 'Releases', link: 'https://github.com/Case211/remnawave-admin/releases' },
          { text: 'Telegram chat', link: 'https://t.me/remnawave_admin' },
          { text: 'Issues', link: 'https://github.com/Case211/remnawave-admin/issues' },
        ],
      },
    ],

    sidebar: {
      '/en/guide/': [
        {
          text: 'Getting started',
          items: [
            { text: 'What it is', link: '/en/guide/overview' },
            { text: 'Server requirements', link: '/en/guide/requirements' },
            { text: 'Installation', link: '/en/guide/installation' },
            { text: 'Upgrading', link: '/en/guide/upgrade' },
          ],
        },
        {
          text: 'Configuration',
          items: [
            { text: 'Web panel and proxy', link: '/en/guide/web-panel' },
            { text: 'Access and roles', link: '/en/guide/access' },
            { text: 'Telegram bot', link: '/en/guide/bot' },
            { text: 'Panel webhook', link: '/en/guide/webhook-setup' },
          ],
        },
        {
          text: 'Nodes',
          items: [
            { text: 'Node Agent', link: '/en/guide/node-agent' },
            { text: 'Torrent detection', link: '/en/guide/torrents' },
          ],
        },
        {
          text: 'Features',
          items: [
            { text: 'Anti-abuse', link: '/en/guide/anti-abuse' },
            { text: 'Mail server', link: '/en/guide/mail' },
            { text: 'Plugins', link: '/en/guide/plugins' },
            { text: 'Monitoring', link: '/en/guide/monitoring' },
            { text: 'Backups', link: '/en/guide/backups' },
          ],
        },
        {
          text: 'Operations',
          items: [
            { text: 'Troubleshooting', link: '/en/guide/troubleshooting' },
            { text: 'Development', link: '/en/guide/development' },
            { text: 'Contributing', link: '/en/guide/contributing' },
          ],
        },
      ],

      '/en/reference/': [
        {
          text: 'Reference',
          items: [
            { text: 'Panel settings', link: '/en/reference/settings' },
            { text: 'Environment variables', link: '/en/reference/env' },
            { text: 'Bot commands', link: '/en/reference/bot-commands' },
            { text: 'Project layout', link: '/en/reference/project-layout' },
          ],
        },
        {
          text: 'Public API',
          items: [
            { text: 'Overview and keys', link: '/en/reference/api' },
            { text: 'Endpoints', link: '/en/reference/api-endpoints' },
            { text: 'Errors', link: '/en/reference/api-errors' },
          ],
        },
        {
          text: 'Outgoing webhooks',
          items: [
            { text: 'Subscriptions and delivery', link: '/en/reference/webhooks' },
            { text: 'Event catalogue', link: '/en/reference/webhook-events' },
            { text: 'Signature verification', link: '/en/reference/webhook-signatures' },
          ],
        },
      ],
    },

    editLink: {
      pattern: 'https://github.com/Case211/remnawave-admin/edit/main/docs/:path',
      text: 'Suggest an edit',
    },
    footer: {
      message: 'AGPL-3.0 with a plugin exception',
      copyright: 'Built for the Remnawave community',
    },
  },
}
