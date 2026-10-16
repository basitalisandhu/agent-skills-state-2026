package main
func tools() {
	a := mcp.NewTool("write_file", mcp.WithDescription("Write"), mcp.WithDestructiveHintAnnotation(true))
	b := &mcp.Tool{Name: "fetch_page", Annotations: &mcp.ToolAnnotations{ReadOnlyHint: true}}
}
func more(srv *mcpsdk.Server) {
	mcpsdk.AddTool(srv, &mcpsdk.Tool{
		Description: "Kill a job",
		Name:        "kill_job",
	}, h)
	x := mcpsdk.Tool{Description: "no name here"}
}
