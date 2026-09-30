<?php

// Run with PHP 8.5: php tests/dmarc-xml.php /path/to/dmarc-srg
$root = $argv[1] ?? '/var/www/admin/dmarc';
spl_autoload_register(function (string $class) use ($root): void {
    $prefix = 'Liuch\\DmarcSrg\\';
    if (str_starts_with($class, $prefix)) {
        require $root . '/classes/' . str_replace('\\', '/', substr($class, strlen($prefix))) . '.php';
    }
});
error_reporting(E_ALL);
set_error_handler(function (int $severity, string $message, string $file, int $line): never {
    throw new ErrorException($message, -1, $severity, $file, $line);
});

function parseReport(string $xml): array
{
    $stream = fopen('php://memory', 'r+');
    try {
        fwrite($stream, $xml);
        rewind($stream);
        return Liuch\DmarcSrg\Report\ReportData::fromXmlFile($stream)->toArray();
    } finally {
        fclose($stream);
    }
}

$data = parseReport(<<<'XML'
<?xml version="1.0"?>
<feedback>
  <report_metadata>
    <org_name>Example</org_name>
    <email>dmarc@example.test</email>
    <report_id>php85-regression</report_id>
    <date_range><begin>1790726400</begin><end>1790812800</end></date_range>
  </report_metadata>
  <policy_published><domain>example.test</domain><p>none</p></policy_published>
  <record>
    <row>
      <source_ip>192.0.2.1</source_ip><count>1</count>
      <policy_evaluated><disposition>none</disposition><dkim>pass</dkim><spf>pass</spf></policy_evaluated>
    </row>
    <identifiers><header_from>example.test</header_from></identifiers>
  </record>
</feedback>
XML);
if (count($data['records']) !== 1 || $data['records'][0]['ip'] !== '192.0.2.1') {
    throw new RuntimeException('Valid DMARC report was not parsed correctly');
}

try {
    parseReport('<feedback><record></feedback>');
    throw new RuntimeException('Malformed XML was accepted');
} catch (Liuch\DmarcSrg\Exception\RuntimeException $e) {
    if ($e->getMessage() !== 'Incorrect XML report file') {
        throw $e;
    }
}

echo "DMARC XML regression tests passed\n";
