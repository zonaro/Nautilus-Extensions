# Plano de modularização — Nautilus Extensions

> Proposta técnica; nenhuma alteração de código foi realizada.

## Diretrizes
- Manter Python, GTK 4, libadwaita e integração nautilus-python.
- Preservar sincronização com ToFpon/Nautilus-Extensions e créditos GPL-3.0.
- Refatorar incrementalmente, sem mover em massa os arquivos herdados.

## Diagnóstico preliminar
- O instalador oferece 28 extensões e seleção por --only/--exclude.
- media_core já centraliza parte da conversão multimídia.
- Há traduções embutidas em módulos como audio-tools.py e video-tools.py.
- A landing page está em docs/ com catálogo e traduções próprios.

## Arquitetura sugerida
- shared/i18n: traduções e fallback.
- shared/dependencies: detecção de programas externos.
- shared/jobs: subprocessos, cancelamento e progresso.
- media_core: manter e testar o núcleo existente.
- adapters/nautilus: integrar menus e ações gradualmente.
- tests: testes unitários e de integração.

## Auditoria e prioridades
1. Mapear dependências e proveniência de cada extensão.
2. Testar instalação seletiva, atualização e desinstalação em Fedora, Ubuntu, Arch e openSUSE.
3. Verificar se hidden-dim-all e hidden-dim-icon são mutuamente exclusivos.
4. Revisar ConversionRegistry.get_backend(): seleção de Pillow para saída de imagem não consulta explicitamente can_convert para o par de formatos.
5. Testar conversões inválidas, cancelamentos, colisões de arquivos e ausência de dependências.
6. Revisar subprocessos bloqueantes na interface do Nautilus.
7. Centralizar traduções gradualmente, preservando idiomas.
8. Adicionar CI, lint e testes sem reformatação massiva dos arquivos upstream.
9. Sincronizar README, documentação e landing page com o comportamento efetivo.

## Estratégia upstream
- Classificar cada arquivo como herdado, modificado ou exclusivo.
- Manter alterações locais pequenas e identificáveis.
- Preferir adaptadores e módulos compartilhados a mudanças profundas no código herdado.
- Fazer merge upstream somente após revisão do diff e testes de regressão.

## Critérios de aceite
- Instalação seletiva confiável e reversível.
- Nenhuma regressão funcional confirmada.
- Testes automatizados dos fluxos críticos.
- Licenças e atribuições preservadas.
- Compatibilidade e dependências documentadas por distribuição.

## Observação
Os itens de auditoria são hipóteses a verificar, não bugs confirmados. A estrutura de pastas é uma proposta e deve ser validada contra imports e empacotamento antes da implementação.
