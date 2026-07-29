# Painel de ciclos Thoms

Vocabulário canônico usado para analisar e comparar ciclos térmicos no painel do Frigorífico Thoms.

## Fases do ciclo

**Carregamento**:
Período entre a ativação do sinal de carregamento e o início do resfriamento.
_Evitar_: Carga

**Resfriamento até a meta**:
Período entre o início do resfriamento e a primeira leitura em que a temperatura do espeto fica menor ou igual a 7 °C.
_Evitar_: Resfriamento pré-meta, resfriamento inicial

**Resfriamento pós-meta**:
Período iniciado na primeira leitura em que a temperatura do espeto fica menor ou igual a 7 °C e encerrado no fim do ciclo. A classificação não regride se a temperatura subir novamente.
_Evitar_: Resfriamento final, pós-resfriamento

**Hora da fase**:
Tempo decorrido desde o início da fase atual. A contagem reinicia em zero no carregamento, no resfriamento até a meta e no resfriamento pós-meta, sem alterar a duração real de cada fase.
_Evitar_: Hora normalizada, percentual da fase

**Rótulo horário da fase**:
Código formado pela fase e pela hora decorrida: C para carregamento, R para resfriamento até a meta e P para resfriamento pós-meta.
_Evitar_: H0, hora do ciclo

**Média horária da fase**:
Média das amostras válidas de uma variável dentro de uma hora da fase. É o valor comum apresentado nas barras e na tabela explicativa.
_Evitar_: Valor horário, dado da barra

**Hora parcial**:
Hora da fase com menos de 45 minutos de cobertura observada. Seu valor permanece disponível, acompanhado da duração efetivamente coberta.
_Evitar_: Hora incompleta, dado inválido

## Desempenho

**Leitura de peso valida**:
Leitura da balanca maior que 90 kg. Leituras ausentes, zero, negativas ou iguais ou menores que 90 kg nao entram no calculo da perda.
_Evitar_: peso bruto, primeira leitura disponivel

**Peso de referencia**:
Primeira leitura de peso valida exatamente cinco minutos depois da amostra de maior peso durante o carregamento. E o denominador da perda de peso ate a meta.
_Evitar_: peso inicial, peso do pico

**Perda de peso ate 7 C**:
Percentual entre o peso de referencia e a leitura de peso valida no instante da primeira leitura de espeto menor ou igual a 7 C: `(peso de referencia - peso aos 7 C) / peso de referencia x 100`. Se qualquer uma das duas leituras nao existir, o indicador fica indisponivel.
_Evitar_: perda total do ciclo, perda estimada

**Desempenho do ciclo**:
Relação entre o tempo necessário para o espeto atingir 7 °C e a perda percentual de peso até esse instante. Os dois resultados permanecem visíveis separadamente, sem presumir que um deles sempre prevalece.
_Evitar_: Eficiência, ciclo vencedor

**Ciclo sugerido**:
Ciclo válido classificado entre os três melhores equilíbrios entre tempo até 7 °C e perda percentual de peso, com ponderação igual entre os dois indicadores.
_Evitar_: Melhor ciclo, ciclo vencedor

**Meta não atingida**:
Condição de um ciclo encerrado sem leitura do espeto menor ou igual a 7 °C. Todo o seu resfriamento permanece na fase R e não existe fase P.
_Evitar_: Ciclo incompleto, ciclo inválido

**Leitura da seleção**:
Síntese determinística dos resultados dos ciclos selecionados, destacando rapidez, perda de peso, equilíbrio entre ambos e diferenças de duração sem atribuir causalidade.
_Evitar_: Diagnóstico automático, recomendação da IA

## Relatórios

**Relatório da seleção**:
Registro em PDF dos ciclos, janela de análise e variáveis selecionados no painel no momento da geração.
_Evitar_: Relatório completo, relatório do ciclo
