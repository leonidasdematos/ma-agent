# ma-agent

Gateway agent for Monitor Agrícola (Raspberry ↔ Android)

## Visão geral

Este repositório contém o esqueleto do novo gateway **Codex** que fará a
ponte entre os dispositivos de campo (Raspberry Pi, receptores GNSS,
implementos) e o monitor agrícola Android. O foco inicial é garantir uma
camada de comunicação sólida, simples e extensível para evoluir o
sistema por etapas.

### Arquitetura

* `ma_agent/agent.py` — ponto de entrada usado pelo `systemd`.
* `ma_agent/` — pacote Python com as camadas de configuração,
  transporte (TCP/Bluetooth), protocolo de mensagens e regras de
  negócio da sessão.

Os módulos expõem um serviço `GatewayService` que inicia servidores TCP e
Bluetooth RFCOMM (quando disponível) e processa mensagens JSON
terminadas por `\n`. O handshake `HELLO → HELLO_ACK` é obrigatório
antes de qualquer outra mensagem, garantindo que o monitor reconheça a
versão do agente e as capacidades habilitadas.

### Fluxo de mensagens

1. **HELLO** — enviado pelo monitor; responde com `HELLO_ACK` contendo
   versão e lista de capacidades.
2. **PING** — testes de vida; responde com `PONG`.
3. **INFO / GET_STATUS** — dados gerais e estado atual (job em execução).
4. **START_JOB / STOP_JOB** — controle do trabalho atual.
5. **UPDATE** — recebe um pacote `.zip` em base64, grava em disco e
   aplica a atualização.
6. **REBOOT** — solicita reinicialização do gateway.

Os manipuladores estão concentrados em `ma_agent/session.py` e foram
pensados para evoluir com novos tipos de mensagem (telemetria GNSS,
implementos ISOBUS, etc.).

### Como executar localmente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pybluez  # opcional, necessário apenas para testes BT
# opcional: informar o arquivo de configuração do implemento
export MA_AGENT_IMPLEMENT_CONFIG=$(pwd)/config/implement.vence_tudo.json
python -m ma_agent.agent
```

Para simular um cliente via TCP:

```bash
echo '{"type":"HELLO","payload":{}}' | nc 127.0.0.1 7777
```
### Configuração do implemento

Cada gateway pode atuar com funções distintas (plantadeira, pulverizador,
etc.). O arquivo `config/implement.vence_tudo.json` descreve o equipamento
utilizado neste ambiente de desenvolvimento: uma plantadeira **Vence
Tudo** com 26 linhas espaçadas a cada 0,5 m, distância de 4 m entre o
rabicho e a primeira linha, 26 seções de sementes e 2 de adubo, todas com
suporte a taxa variável.

Durante a inicialização, o agente tenta carregar o arquivo apontado pela
variável `MA_AGENT_IMPLEMENT_CONFIG`. Caso não exista, um perfil padrão
com as mesmas características acima (empacotado no código fonte) é
utilizado e enviado ao monitor via mensagem `INFO`.


### Simulador de plantio

O agente inclui um simulador opcional que publica coordenadas GNSS e o
estado da plantadeira durante testes locais. Por padrão ele está
habilitado e pode ser ajustado via variáveis de ambiente:

```bash
export MA_AGENT_ENABLE_SIMULATOR=1            # ativa/desativa o simulador
export MA_AGENT_SIM_FIELD_LENGTH_M=250        # comprimento do talhão (m)
export MA_AGENT_SIM_HEADLAND_M=18             # comprimento da cabeceira (m)
export MA_AGENT_SIM_SPEED_MPS=2.8             # velocidade média (m/s)
export MA_AGENT_SIM_SAMPLE_HZ=2.0             # taxa de envio (Hz)
export MA_AGENT_SIM_PASSES_PER_CYCLE=10       # número de idas/voltas no ciclo
```

O simulador percorre um trajeto em “zigue-zague”: realiza um tiro com a
plantadeira ligada, executa a manobra de cabeceira com as linhas
desligadas e retorna pela linha adjacente, garantindo que o monitor
repinte o mapa corretamente.


### Próximos passos

* Adicionar autenticação e criptografia conforme necessário.
* Instrumentar métricas e testes automatizados.