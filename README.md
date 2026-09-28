# TV Garden Brasil → M3U automática

Gerador de playlist M3U para os canais do Brasil apresentados pelo TV Garden.

## Fonte

- TV Garden Brasil: https://tvgarden.world/tv/br
- Fonte de dados utilizada pelo TV Garden: IPTV-org — https://iptv-org.github.io/iptv/countries/br.m3u

O TV Garden informa que seus canais são obtidos principalmente do IPTV-org e que aplica critérios técnicos como HTTPS e reprodução externa.

## Arquivos gerados na raiz

- `lista.m3u` — playlist final para SS IPTV.
- `descoberto.json` — relatório completo da última execução.
- `status.json` — resumo da execução.
- `fontes.json` — configuração das fontes e filtros.

## Atualização

O GitHub Actions executa automaticamente a cada 6 horas.

Também é possível executar manualmente em:

**GitHub → Actions → Atualizar lista TV Garden Brasil → Run workflow**

## Filtros

1. Brasil.
2. HTTPS.
3. Teste individual de cada stream.
4. Streams que falharem no teste são removidos.
5. Duplicatas são removidas.
6. `tvg-name`, `tvg-id`, logo e `group-title` são preservados quando disponíveis.

## Link da playlist

Depois de enviar o projeto para seu GitHub, o arquivo ficará disponível em:

`https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPOSITORIO/main/lista.m3u`

Substitua `SEU_USUARIO/SEU_REPOSITORIO` pelos dados do seu repositório.
