impl Fixture {
    #[tool(description = "Purge cache", annotations(destructive_hint = true, idempotent_hint = true))]
    async fn purge_cache(&self) -> String { String::new() }
    #[tool(description = "Show status")]
    async fn show_status(&self) -> String { String::new() }
}
