# Configurer les agents avec mc-iclone8-mcp

Démarrer le serveur dans iClone 8 avant de connecter un agent :

```text
http://127.0.0.1:8766/mcp
```

Le serveur utilise MCP Streamable HTTP. Il ne faut pas le configurer en
`stdio`, `sse` ou avec une URL distante.

## Codex

```powershell
codex mcp add mc-iclone8-mcp --url http://127.0.0.1:8766/mcp
codex mcp list
```

## Claude Code

```powershell
claude mcp add --transport http mc-iclone8-mcp http://127.0.0.1:8766/mcp --scope user
claude mcp list
```

Pour un projet partagé, remplacer `--scope user` par `--scope project`.

## Pi coding agent

Dans le fichier MCP de Pi (`mcp.json` ou celui fourni par l’extension MCP) :

```json
{
  "mcpServers": {
    "mc-iclone8-mcp": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8766/mcp"
    }
  }
}
```

Si la distribution Pi ne fournit pas de client MCP, installer l’extension ou
le paquet MCP recommandé par cette distribution, puis vérifier que les outils
apparaissent dans la liste de Pi.

## OpenClaw

```json
{
  "mcpServers": {
    "mc-iclone8-mcp": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8766/mcp"
    }
  }
}
```

La commande ou l’interface exacte dépend de la version d’OpenClaw. Vérifier
`openclaw mcp --help`. `openclaw mcp serve` sert principalement à exposer
OpenClaw comme serveur/pont MCP et ne remplace pas forcément le client MCP.

## VS Code

Créer `.vscode/mcp.json` dans le projet :

```json
{
  "servers": {
    "mc-iclone8-mcp": {
      "type": "http",
      "url": "http://127.0.0.1:8766/mcp"
    }
  }
}
```

Utiliser **MCP: List Servers** ou **MCP: Start Server**, puis vérifier les
outils dans le mode Copilot/Agent.

## Hermes et autres clients MCP

Si le client accepte MCP Streamable HTTP, utiliser :

```json
{
  "name": "mc-iclone8-mcp",
  "type": "streamable-http",
  "url": "http://127.0.0.1:8766/mcp"
}
```

Selon le client, l’objet doit être placé sous `mcpServers`, `servers` ou dans
un champ graphique. Si Hermes ne prend en charge que `stdio`, il faut un
adaptateur MCP HTTP→stdio ; le plugin iClone n’en fournit pas.

## Installer le skill expert

Copier le dossier [`skills/iclone8-mcp`](../skills/iclone8-mcp) dans le dossier
de skills de l’agent :

```text
Codex       : %USERPROFILE%\.codex\skills\iclone8-mcp
Claude Code : .claude\skills\iclone8-mcp
Projet      : .agents\skills\iclone8-mcp
```

Le skill formalise l’inspection préalable, les confirmations destructives, la
vérification des résultats et la formulation des prompts iClone 8.

## Test sans modification

Après le démarrage du serveur, demander à l’agent :

> Utilise mc-iclone8-mcp. Vérifie la connexion, liste les outils disponibles et liste les objets de la scène sans rien modifier.

L’agent doit commencer par `ping_iclone` ou `get_api_version` et ne doit créer,
supprimer ou animer aucun objet pour ce test.
