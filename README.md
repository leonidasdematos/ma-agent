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
Tudo** articulada com 26 linhas espaçadas a cada 0,5 m, distância de
1,5 m entre a antena e o ponto de articulação, mais 4 m do engate até as
linhas finais, 26 seções de sementes e 2 de adubo, todas com suporte a
taxa variável.

Durante a inicialização, o agente tenta carregar o arquivo apontado pela
variável `MA_AGENT_IMPLEMENT_CONFIG`. Caso não exista, um perfil padrão
com as mesmas características acima (empacotado no código fonte) é
utilizado e enviado ao monitor via mensagem `INFO`.

> **Instrução rápida para o monitor Android:** ao receber o payload do
> implemento com `"articulated": true`, utilize os campos
> `"antenna_to_articulation_m"` e `"articulation_to_tool_m"` para
> reconstruir a geometria. O primeiro define a distância da antena até o
> ponto de engate, enquanto o segundo representa o comprimento entre o
> engate e o centro das linhas — exatamente o que o helper articulado do
> gateway envia durante a telemetria. Usando esses valores, o monitor
> consegue posicionar o ponto de articulação e a barra final de forma
> consistente com o modelo usado pelo gateway.



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

Quando for necessário testar cenários específicos (curvas, terraços ou
talhões irregulares) defina o arquivo `MA_AGENT_SIM_ROUTE_FILE` apontando
para uma lista de pontos ENU (`east_m`/`north_m`) ou um GeoJSON com
coordenadas geográficas. Também é possível indicar o formato explicitando
`MA_AGENT_SIM_ROUTE_FORMAT=json|geojson`. O repositório já inclui um
exemplo (`config/routes/terrace_demo.json`) que descreve duas passadas
acompanhando curvas de nível, com trechos ativos e manobras desligadas:

```json
{
  "description": "Curved terrace-following route with two passes",
  "points": [
    {"east_m": -5.0, "north_m": -35.0, "active": false},
    {"east_m": 6.0, "north_m": 0.0, "active": true},
    {"east_m": 19.0, "north_m": 220.0, "active": false}
  ]
}
```

Basta apontar `MA_AGENT_SIM_ROUTE_FILE=$(pwd)/config/routes/rota_plantio_terracos.geojson`
antes de iniciar o agente para que o simulador reproduza o trajeto. Também é
possível informar apenas o nome do arquivo (ex.: `MA_AGENT_SIM_ROUTE_FILE=rota_plantio_terracos.geojson`),
pois o simulador busca automaticamente em `config/routes/` quando o caminho não
for absoluto.
### Como usar o cálculo articulado

O módulo `ma_agent.articulation` reproduz a cinemática utilizada pelo
monitor Android para estimar a posição do implemento quando o gateway
está operando no modo **articulado**. Ele recebe as posições da antena do
trator, os vetores de orientação (`forward`/`right`) e as distâncias de
instalação para calcular automaticamente:

* o ponto de articulação (engate) no referencial local ENU;
* o centro do implemento no passo atual e no passo anterior;
* o eixo (vetor unitário) alinhado ao implemento, útil para desenhar a
  barra ou calcular derrapagem;
* um indicador se o deslocamento do implemento foi significativo o
  bastante para atualizar o mapa.

O fluxo básico é sempre o mesmo: inicialize o cache do ângulo do
implemento com `None`, invoque `compute_articulated_centers` a cada novo
pacote GNSS do trator e armazene o ângulo retornado para a próxima
iteração. O exemplo abaixo mostra como integrar o cálculo com os dados
que já existem no gateway:

```python
from ma_agent.articulation import Coordinate, compute_articulated_centers

impl_theta = None  # cache persistido entre as iterações

def handle_step(sample):
    global impl_theta

    result = compute_articulated_centers(
        last_xy=Coordinate(*sample.last_antena_xy_m),
        cur_xy=Coordinate(*sample.cur_antena_xy_m),
        fwd=sample.forward_vector,
        right=sample.right_vector,
        distancia_antena=sample.distancia_antena_m,
        offset_longitudinal=sample.offset_longitudinal_m,
        offset_lateral=sample.offset_lateral_m,
        work_width_m=sample.work_width_m,
        impl_theta_rad=impl_theta,
        tractor_heading_rad=sample.heading_rad,
        previous_displacement=sample.prev_displacement,
        last_fwd=sample.last_forward_vector,
        last_right=sample.last_right_vector,
    )

    # Persista o heading do implemento para o próximo passo.
    impl_theta = result.theta

    # Use os pontos calculados para atualizar o monitor.
    gateway.send_articulation_update(
        articulation_xy=(result.articulation_point.x, result.articulation_point.y),
        implement_xy=(result.current_center.x, result.current_center.y),
        axis=result.axis,
        has_motion=result.significant_motion,
    )
```

Todos os parâmetros são expressos em metros e radianos no sistema de
coordenadas local (ENU). Para manter a estabilidade, o helper cuida dos
limiares mínimos de deslocamento (`EPS_STEP`, `EPS_IMPL`) e faz o
“wrap” dos ângulos automaticamente.


### Próximos passos

* Adicionar autenticação e criptografia conforme necessário.
* Instrumentar métricas e testes automatizados.