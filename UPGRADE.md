# Upgrade

## 1.4.x -> 1.5.0
```sql
ALTER TABLE `valias` ADD `valias_type` TINYINT NULL DEFAULT '1' COMMENT '1=forwarder 0=lda' FIRST;
ALTER TABLE `valias` ADD `copy` TINYINT NULL DEFAULT '0' COMMENT '0=redirect 1=copy&redirect' AFTER `valias_line`;
```

REMOVE PRIMARY KEY FROM VPOPMAIL