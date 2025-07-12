WAREHOUSE_XMLA_JSON = {
    'name': '{{Dataset_Name}}',
    'compatibilityLevel': 1604,
    'model': {
        'name': '{{Dataset_Name}}',
        'culture': 'en-US',
        'collation': 'Latin1_General_100_BIN2_UTF8',
        'dataAccessOptions': {
            'legacyRedirects': True,
            'returnErrorValuesAsNull': True,
        },
        'defaultPowerBIDataSourceVersion': 'powerBI_V3',
        'sourceQueryCulture': 'en-US',
        'expressions': [
            {
                'name': 'DatabaseQuery',
                'kind': 'm',
                'expression': 'let\n    database = {{TDS_Endpoint}}\nin\n    database\n',
            }
        ],
        'annotations': [
            {'name': '__PBI_TimeIntelligenceEnabled', 'value': '0'},
            {
                'name': 'SourceLineageTagType',
                'value': 'DatabaseFullyQualifiedName',
            },
        ],
    },
}

WAREHOUSE_DEFAULT_SEMANTIC_MODEL_TXT = 'Has default semantic model'

WAREHOUSE_SQL_PROJECT = """<Project DefaultTargets="Build">
  <Sdk Name="Microsoft.Build.Sql" Version="0.1.19-preview" />
  <PropertyGroup>
    <Name>{warehouse_display_name}</Name>
    <DSP>Microsoft.Data.Tools.Schema.Sql.SqlDwUnifiedDatabaseSchemaProvider</DSP>
    <DefaultCollation>Latin1_General_100_BIN2_UTF8</DefaultCollation>
  </PropertyGroup>
  <Target Name="BeforeBuild">
    <Delete Files="$(BaseIntermediateOutputPath)\project.assets.json" />
  </Target>
</Project>"""
