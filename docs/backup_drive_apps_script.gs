/**
 * Omega Studio · recebe os backups do sistema e salva na pasta
 * "Omega Studio/Backups" do Google Drive do Pedro.
 *
 * Como instalar (uma vez só):
 * 1. Abra https://script.google.com com a conta pedro.ruan11@gmail.com → Novo projeto.
 * 2. Apague o conteúdo e cole este arquivo inteiro. Salve com o nome "Omega Backup".
 * 3. Engrenagem (Configurações do projeto) → Propriedades do script → Adicionar:
 *      SEGREDO = (o mesmo valor da variável DRIVE_BACKUP_SEGREDO do Render)
 * 4. Implantar → Nova implantação → Tipo: App da Web
 *      Executar como: Eu  ·  Quem pode acessar: Qualquer pessoa
 *    Autorize o acesso ao Drive quando o Google pedir.
 * 5. Copie a URL do app da Web (termina em /exec) e coloque no Render como DRIVE_BACKUP_URL.
 */
var PASTA_ID = '10JS8b8AzeaBROZoMH1w3Grf5K__pmyaq'; // Omega Studio/Backups
var MANTER = 60; // quantos arquivos guardar na pasta

function doPost(e) {
  try {
    var dados = JSON.parse(e.postData.contents);
    var segredo = PropertiesService.getScriptProperties().getProperty('SEGREDO');
    if (!segredo || dados.segredo !== segredo) {
      return resposta({ ok: false, erro: 'segredo inválido' });
    }
    var nome = String(dados.nome || 'omega-backup.json.gz').replace(/[^\w.\-]/g, '_');
    var bytes = Utilities.base64Decode(dados.conteudo);
    var pasta = DriveApp.getFolderById(PASTA_ID);
    var arquivo = pasta.createFile(Utilities.newBlob(bytes, 'application/gzip', nome));
    limparAntigos(pasta);
    return resposta({ ok: true, arquivo: arquivo.getName() });
  } catch (err) {
    return resposta({ ok: false, erro: String(err) });
  }
}

function limparAntigos(pasta) {
  var arquivos = [];
  var it = pasta.getFiles();
  while (it.hasNext()) {
    var f = it.next();
    if (f.getName().indexOf('omega-backup-') === 0) arquivos.push(f);
  }
  arquivos.sort(function (a, b) { return b.getDateCreated() - a.getDateCreated(); });
  for (var i = MANTER; i < arquivos.length; i++) arquivos[i].setTrashed(true);
}

function resposta(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
