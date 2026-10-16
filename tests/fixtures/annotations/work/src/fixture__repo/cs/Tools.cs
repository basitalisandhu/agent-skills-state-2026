public static class Tools {
    [McpServerTool(ReadOnly = true, OpenWorld = false), Description("Read a record")]
    public static string ReadRecord(string id) => id;
    [McpServerTool, Description("Terminate a session")]
    public static string TerminateSession(string id) => id;
}
