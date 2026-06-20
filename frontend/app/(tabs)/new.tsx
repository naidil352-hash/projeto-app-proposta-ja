import React, { useEffect, useState } from "react";
import {
  View,
  Image,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
  useWindowDimensions,
} from "react-native";

import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { useRouter, useLocalSearchParams } from "expo-router";

import { api, formatApiError } from "../../src/api";
import { theme, formatCurrency } from "../../src/theme";
import {
  maskDocument,
  maskPhoneBR,
  maskCurrency,
  formatCurrencyFromBackend,
  parseCurrency,
  parseNumber,
} from "../../src/masks";

import UpgradeModal from "../../src/UpgradeModal";

type Product = {
  id: string;
  product_id?: string;
  code?: string;
  name: string;
  description?: string;
  unit?: string;
  quantity: string;
  price: string;
};

type CatalogProduct = {
  id: string;
  code: string;
  name: string;
  description: string;
  price: number;
  unit: string;
};

export default function NewProposal() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;

  const params = useLocalSearchParams();
  const editId = typeof params.editId === "string" ? params.editId : null;
  const isEditing = !!editId;

  const [clientName, setClientName] = useState("");
  const [doc, setDoc] = useState("");
  const [phone, setPhone] = useState("");
  const [deadline, setDeadline] = useState("");
  const [notes, setNotes] = useState("");
  const [discount, setDiscount] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("");
  const [validity, setValidity] = useState("15");
  const [images, setImages] = useState<string[]>([]);
  
  const [products, setProducts] = useState<Product[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCatalogProduct, setSelectedCatalogProduct] = useState<CatalogProduct | null>(null);
  const [quantityInput, setQuantityInput] = useState("1");
  const [showDropdown, setShowDropdown] = useState(false);

  const [itemType, setItemType] = useState<"catalog" | "manual">("catalog");
  const [manualName, setManualName] = useState("");
  const [manualDesc, setManualDesc] = useState("");
  const [manualUnit, setManualUnit] = useState("UN");
  const [manualPrice, setManualPrice] = useState("");
  const [manualQty, setManualQty] = useState("1");

  const [catalogProducts, setCatalogProducts] = useState<CatalogProduct[]>([]);
  const [loadingCatalog, setLoadingCatalog] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingProposal, setLoadingProposal] = useState(false);
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [upgradeMsg, setUpgradeMsg] = useState<string | undefined>();
  
  // Controla qual item está com o dropdown ativo focado para evitar sobreposição visual
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);

    const reset = () => {
    setClientName("");
    setDoc("");
    setPhone("");
    setDeadline("");
    setNotes("");
    setDiscount("");
    setPaymentTerms("");
    setValidity("15");
    setImages([]);
    setProducts([]);
    setSearchQuery("");
    setSelectedCatalogProduct(null);
    setQuantityInput("1");
    setShowDropdown(false);
    setItemType("catalog");
    setManualName("");
    setManualDesc("");
    setManualUnit("UN");
    setManualPrice("");
    setManualQty("1");
  };
  useEffect(() => {
    if (!editId) {
      reset();
      return;
    }

    const loadProposal = async () => {
      try {
        setLoadingProposal(true);
        const { data } = await api.get(`/proposals/${editId}`);

        setClientName(data.client_name || "");
        setDoc(data.client_document || "");
        setPhone(data.client_phone || "");
        setDeadline(data.shipping_deadline || "");
        setNotes(data.notes || "");
        setDiscount(formatCurrencyFromBackend(data.discount || ""));
        setPaymentTerms(data.payment_terms || "");
        setValidity(String(data.validity_days || 15));
        setImages(Array.isArray(data.images) ? data.images : []);

                if (data.products && data.products.length) {
          setProducts(
            data.products.map((p: any) => ({
              id: crypto.randomUUID(),
              product_id: p.product_id || undefined,
              code: p.code || undefined,
              name: p.name || "",
              description: p.description || "",
              unit: p.unit || "UN",
              quantity: String(p.quantity || ""),
              price: formatCurrencyFromBackend(p.unit_price || p.price || 0),
            }))
          );
        }
      } catch (e) {
        Alert.alert("Erro", "Não foi possí­vel carregar proposta");
      } finally {
        setLoadingProposal(false);
      }
    };

    loadProposal();
  }, [editId]);

  useEffect(() => {
    const loadCatalog = async () => {
      try {
        setLoadingCatalog(true);
        const { data } = await api.get("/products");
        setCatalogProducts(Array.isArray(data) ? data : []); 	
      } catch (e) {
        console.log("Erro carregando catálogo", e);
      } finally {
        setLoadingCatalog(false);
      }
    };

    loadCatalog();
  }, []);

	  const removeProduct = (i: number) => {
    setProducts((prev) => prev.filter((_, idx) => idx !== i));
  };

  const handleAddItem = () => {
    if (itemType === "catalog") {
      if (!selectedCatalogProduct) {
        Alert.alert("Erro", "Selecione um produto do catálogo primeiro.");
        return;
      }
      const qty = parseNumber(quantityInput);
      if (qty <= 0) {
        Alert.alert("Erro", "A quantidade deve ser maior que zero.");
        return;
      }

      setProducts((prev) => {
        const existingIdx = prev.findIndex((p) => p.product_id === selectedCatalogProduct.id);
        if (existingIdx >= 0) {
          return prev.map((p, idx) =>
            idx === existingIdx
              ? {
                  ...p,
                  quantity: String(parseNumber(p.quantity) + qty),
                }
              : p
          );
        }
        return [
          ...prev,
          {
            id: crypto.randomUUID(),
            product_id: selectedCatalogProduct.id,
            code: selectedCatalogProduct.code,
            name: selectedCatalogProduct.name,
            description: selectedCatalogProduct.description,
            unit: selectedCatalogProduct.unit || "UN",
            quantity: String(qty),
            price: formatCurrencyFromBackend(selectedCatalogProduct.price),
          },
        ];
      });

      setSelectedCatalogProduct(null);
      setSearchQuery("");
      setQuantityInput("1");
    } else {
      if (!manualName.trim()) {
        Alert.alert("Erro", "O nome do item é obrigatório.");
        return;
      }
      const qty = parseNumber(manualQty);
      if (qty <= 0) {
        Alert.alert("Erro", "A quantidade deve ser maior que zero.");
        return;
      }
      const parsedPrice = parseCurrency(manualPrice);
      if (parsedPrice < 0) {
        Alert.alert("Erro", "O preço unitário deve ser maior ou igual a zero.");
        return;
      }

      setProducts((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          name: manualName.trim(),
          description: manualDesc.trim(),
          unit: manualUnit.trim() || "UN",
          quantity: String(qty),
          price: formatCurrencyFromBackend(parsedPrice),
        },
      ]);

      setManualName("");
      setManualDesc("");
      setManualUnit("UN");
      setManualPrice("");
      setManualQty("1");
    }
  };

  const renderItemsSection = () => {
    const search = searchQuery.toLowerCase().trim();
    const filteredCatalog = !search
      ? catalogProducts
      : catalogProducts.filter((cp) => {
          const cpCode = cp.code.toLowerCase();
          const cpName = cp.name.toLowerCase();
          return cpCode.includes(search) || cpName.includes(search);
        });

    return (
      <View style={{ gap: 12 }}>
        {/* Selector Tabs */}
        <View style={{ flexDirection: "row", gap: 8 }}>
          <TouchableOpacity
            style={[
              s.tabButton,
              itemType === "catalog" && s.tabButtonActive
            ]}
            onPress={() => setItemType("catalog")}
          >
            <Text style={[s.tabButtonText, itemType === "catalog" && s.tabButtonTextActive]}>
              + Produto do Catálogo
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[
              s.tabButton,
              itemType === "manual" && s.tabButtonActive
            ]}
            onPress={() => setItemType("manual")}
          >
            <Text style={[s.tabButtonText, itemType === "manual" && s.tabButtonTextActive]}>
              + Item Avulso
            </Text>
          </TouchableOpacity>
        </View>

        <View style={s.selectorBox}>
          {itemType === "catalog" ? (
            <>
              <View style={{ zIndex: 999 }}>
                <Input
                  label="Buscar Produto no Catálogo"
                  value={searchQuery}
                  onChangeText={(v: string) => {
                    setSearchQuery(v);
                    setShowDropdown(true);
                  }}
                  onFocus={() => setShowDropdown(true)}
                  placeholder="Nome ou código do produto..."
                />
                {showDropdown && filteredCatalog.length > 0 && (
                  <View style={s.catalogList}>
                    <ScrollView keyboardShouldPersistTaps="handled" style={{ maxHeight: 200 }}>
                      {filteredCatalog.slice(0, 10).map((cp) => (
                        <TouchableOpacity
                          key={cp.id}
                          style={s.catalogItem}
                          onPress={() => {
                            setSelectedCatalogProduct(cp);
                            setSearchQuery(cp.code + " - " + cp.name);
                            setShowDropdown(false);
                          }}
                        >
                          <Text style={s.catalogItemText}>
                            <Text style={{ fontWeight: "bold" }}>{cp.code}</Text> - {cp.name} ({formatCurrency(cp.price)})
                          </Text>
                        </TouchableOpacity>
                      ))}
                    </ScrollView>
                  </View>
                )}
              </View>

              {selectedCatalogProduct && (
                <View style={s.selectedProductInfo}>
                  <Text style={s.selectedProductText}>
                    Selecionado: {selectedCatalogProduct.code} - {selectedCatalogProduct.name} ({formatCurrency(selectedCatalogProduct.price)})
                  </Text>
                </View>
              )}

              <View style={{ flexDirection: "row", gap: 8, alignItems: "flex-end", marginTop: 4 }}>
                <View style={{ flex: 1 }}>
                  <Input
                    label="Qtd"
                    value={quantityInput}
                    onChangeText={(v: string) => setQuantityInput(v.replace(/[^0-9,.]/g, ""))}
                    keyboardType="numeric"
                    placeholder="1"
                  />
                </View>
                <TouchableOpacity style={s.addButton} onPress={handleAddItem}>
                  <Text style={s.addButtonText}>Adicionar</Text>
                </TouchableOpacity>
              </View>
            </>
          ) : (
            <>
              <Input
                label="Nome *"
                value={manualName}
                onChangeText={setManualName}
                placeholder="Ex: Serpentina FCU 12TR"
              />
              <Input
                label="Descrição"
                value={manualDesc}
                onChangeText={setManualDesc}
                placeholder="Ex: 8 filas tubo 3/8"
              />
              <View style={{ flexDirection: "row", gap: 8 }}>
                <View style={{ flex: 1 }}>
                  <Input
                    label="Unidade"
                    value={manualUnit}
                    onChangeText={setManualUnit}
                    placeholder="UN"
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Input
                    label="Preço Unitário *"
                    value={manualPrice}
                    onChangeText={(v: string) => setManualPrice(maskCurrency(v))}
                    keyboardType="numeric"
                    placeholder="0,00"
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Input
                    label="Qtd *"
                    value={manualQty}
                    onChangeText={(v: string) => setManualQty(v.replace(/[^0-9,.]/g, ""))}
                    keyboardType="numeric"
                    placeholder="1"
                  />
                </View>
              </View>
              <TouchableOpacity style={[s.addButton, { marginTop: 4 }]} onPress={handleAddItem}>
                <Text style={s.addButtonText}>Adicionar Item Avulso</Text>
              </TouchableOpacity>
            </>
          )}
        </View>

        <Text style={s.sectionTitle}>Itens Adicionados</Text>
        {products.length === 0 ? (
          <Text style={{ color: theme.colors.textMuted, fontStyle: "italic", marginVertical: 8 }}>
            Nenhum item adicionado à proposta.
          </Text>
        ) : (
          products.map((p, i) => (
            <View key={p.id} style={s.addedProductRow}>
              <View style={{ flex: 1 }}>
                <Text style={s.addedProductTitle}>
                  {p.code ? (
                    <>
                      <Text style={{ fontWeight: "bold" }}>{p.code}</Text> -{" "}
                    </>
                  ) : null}
                  {p.name}
                </Text>
                {p.description ? (
                  <Text style={s.addedProductDesc}>{p.description}</Text>
                ) : null}
                <Text style={s.addedProductSub}>
                  {p.quantity} Qtd × {formatCurrency(parseCurrency(p.price))} {p.unit ? `(${p.unit})` : ""}
                </Text>
              </View>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
                <Text style={s.addedProductTotal}>
                  {formatCurrency((parseNumber(p.quantity) || 0) * (parseCurrency(p.price) || 0))}
                </Text>
                <TouchableOpacity onPress={() => removeProduct(i)}>
                  <Ionicons name="trash-outline" size={20} color={theme.colors.danger} />
                </TouchableOpacity>
              </View>
            </View>
          ))
        )}
      </View>
    );
  };

  const buildUploadForm = async (asset: any) => {
    const form = new FormData();
    if (Platform.OS === "web") {
      const response = await fetch(asset.uri);
      const blob = await response.blob();
      const name = asset.fileName || asset.uri?.split("/").pop() || "image.jpg";
      form.append("file", blob, name);
    } else {
      form.append("file", {
        uri: asset.uri,
        type: asset.type || "image/jpeg",
        name: asset.fileName || "image.jpg",
      } as any);
    }
    return form;
  };

  const pickImages = async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.7,
        allowsMultipleSelection: true,
      });

      if (result.canceled) return;

      setSaving(true);
      const uploaded: string[] = [];

      for (const asset of result.assets) {
        const form = await buildUploadForm(asset);
        const res = await api.post("/upload/image", form);
        uploaded.push(res.data.url);
      }

      setImages((prev) => [...prev, ...uploaded]);
    } catch (e) {
      Alert.alert("Erro", "Falha ao enviar imagens");
    } finally {
      setSaving(false);
    }
  };

  const removeImage = (url: string) => {
    setImages((prev) => prev.filter((i) => i !== url));
  };

  const subtotal = products.reduce(
    (acc, p) => acc + (parseNumber(p.quantity) || 0) * (parseCurrency(p.price) || 0),
    0
  );
  const discountNum = parseCurrency(discount);
  const total = Math.max(subtotal - discountNum, 0);

  const submit = async () => {
	  console.log("SUBMIT EXECUTOU");
    if (!clientName || !doc || !phone || !deadline) {
      Alert.alert("Atenção", "Preencha cliente, CNPJ/CPF, telefone e prazo.");
      return;
    }

    const cleanProducts = products.map((p) => {
      if (p.product_id) {
        return {
          product_id: p.product_id,
          quantity: parseNumber(p.quantity),
        };
      } else {
        return {
          name: p.name,
          description: p.description || "",
          unit: p.unit || "UN",
          unit_price: parseCurrency(p.price),
          quantity: parseNumber(p.quantity),
        };
      }
    });
    if (!cleanProducts.length) {
      Alert.alert("Atenção", "Adicione pelo menos 1 produto.");
      return;
    }

    try {
      setSaving(true);
	  console.log("PRODUTOS", cleanProducts);
      const payload = {
        client_name: clientName.trim(),
        client_document: doc.trim(),
        client_phone: phone.trim(),
        products: cleanProducts,
        shipping_deadline: deadline.trim(),
        notes: notes.trim(),
        discount: discountNum,
        payment_terms: paymentTerms.trim(),
        images,
        validity_days: parseInt(validity || "15", 10) || 15,
      };
	  console.log("PAYLOAD", payload);
            let response;
      if (isEditing && editId) {
        response = await api.put(`/proposals/${editId}`, payload);
      } else {
        response = await api.post("/proposals", payload);
      }

      reset();
      router.replace(`/proposal/${response.data.id}`);
    } catch (e: any) {
      if (e?.response?.status === 402) {
        setUpgradeMsg(e.response.data?.detail);
        setUpgradeOpen(true);
      } else {
        Alert.alert("Erro", formatApiError(e));
      }
    } finally {
      setSaving(false);
    }
  };

  if (loadingProposal) {
    return (
      <SafeAreaView style={s.root}>
        <ActivityIndicator style={{ marginTop: 80 }} color={theme.colors.primary} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="new-proposal-screen">
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={{ flex: 1 }}
      >
        <View style={s.header}>
          <Text style={s.title}>{isEditing ? "Editar proposta" : "Nova proposta"}</Text>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 }}>
            <Text style={s.subtitle}>Preencha rápido e envie no WhatsApp</Text>
            {loadingCatalog && <ActivityIndicator size="small" color={theme.colors.primary} />}
          </View>
        </View>

        <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
          {isDesktop ? (
            <View style={s.desktopColumns}>
              <View style={s.desktopColumn}>
                <View style={s.panelCard}>
                  <Section title="Cliente">
                    <Input
                      label="Nome *"
                      value={clientName}
                      onChangeText={setClientName}
                      placeholder="Nome do cliente"
                    />

                    <Input
                      label="CNPJ / CPF *"
                      value={doc}
                      onChangeText={(v: string) => setDoc(maskDocument(v))}
                      keyboardType="number-pad"
                      placeholder="000.000.000-00"
                    />

                    <Input
                      label="Telefone *"
                      value={phone}
                      onChangeText={(v: string) => setPhone(maskPhoneBR(v))}
                      keyboardType="phone-pad"
                      placeholder="(11) 99999-9999"
                    />
                  </Section>
                </View>

                                <View style={s.panelCard}>
                  <Section title="Itens">
                    {renderItemsSection()}
                  </Section>
                </View>
              </View>

              <View style={s.desktopColumn}>
                <View style={s.panelCard}>
                  <Text style={s.sectionTitle}>Resumo financeiro</Text>
                  <View style={s.summaryItem}>
                    <Text style={s.summaryLabel}>Subtotal</Text>
                    <Text style={s.summaryValue}>{formatCurrency(subtotal)}</Text>
                  </View>
                  <View style={s.summaryItem}>
                    <Text style={s.summaryLabel}>Desconto</Text>
                    <Text style={s.summaryValue}>{formatCurrency(discountNum)}</Text>
                  </View>
                  <View style={s.summaryItem}>
                    <Text style={s.summaryLabel}>Total</Text>
                    <Text style={s.summaryValue}>{formatCurrency(total)}</Text>
                  </View>
                </View>

                <View style={s.panelCard}>
                  <Section title="Imagens">
                    <TouchableOpacity style={s.imageButton} onPress={pickImages}>
                      <Ionicons name="image-outline" size={22} color="#fff" />
                      <Text style={s.imageButtonText}>Adicionar imagens</Text>
                    </TouchableOpacity>

                    {!!images.length && (
                      <ScrollView
                        horizontal
                        showsHorizontalScrollIndicator={false}
                        contentContainerStyle={{ gap: 10, marginTop: 10 }}
                      >
                        {images.map((img) => (
                          <View key={img} style={s.imageWrap}>
                            <Image source={{ uri: img }} style={s.image} />
                            <TouchableOpacity style={s.removeImage} onPress={() => removeImage(img)}>
                              <Ionicons name="close" size={16} color="#fff" />
                            </TouchableOpacity>
                          </View>
                        ))}
                      </ScrollView>
                    )}
                  </Section>
                </View>

                <View style={s.panelCard}>
                  <Section title="Condições">
                    <Input
                      label="Prazo de embarque *"
                      value={deadline}
                      onChangeText={setDeadline}
                      placeholder="Ex: 15 dias Úteis"
                    />

                    <Input
                      label="Condições de pagamento"
                      value={paymentTerms}
                      onChangeText={setPaymentTerms}
                      placeholder="Ex: 30/60/90 dias"
                    />

                    <View style={{ flexDirection: "row", gap: 8 }}>
                      <View style={{ flex: 1 }}>
                        <Input
                          label="Desconto (R$)"
                          value={discount}
                          onChangeText={(v: string) => setDiscount(maskCurrency(v))}
                          keyboardType="numeric"
                          placeholder="0,00"
                        />
                      </View>

                      <View style={{ flex: 1 }}>
                        <Input
                          label="Validade (dias)"
                          value={validity}
                          onChangeText={(v: string) =>
                            setValidity(v.replace(/\D/g, "").slice(0, 3))
                          }
                          keyboardType="number-pad"
                          placeholder="15"
                        />
                      </View>
                    </View>

                    <Input
                      label="Observações"
                      value={notes}
                      onChangeText={setNotes}
                      placeholder="Opcional"
                      multiline
                    />
                  </Section>
                </View>

                <TouchableOpacity
                  style={[s.cta, saving && { opacity: 0.7 }]}
                  onPress={submit}
                  disabled={saving}
                >
                  {saving ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <>
                      <Ionicons name="checkmark-circle" size={22} color="#fff" />
                      <Text style={s.ctaText}>
                        {isEditing ? "Salvar alterações" : "Criar proposta"}
                      </Text>
                    </>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            <>
              <Section title="Cliente">
                <Input
                  label="Nome *"
                  value={clientName}
                  onChangeText={setClientName}
                  placeholder="Nome do cliente"
                />

                <Input
                  label="CNPJ / CPF *"
                  value={doc}
                  onChangeText={(v: string) => setDoc(maskDocument(v))}
                  keyboardType="number-pad"
                  placeholder="000.000.000-00"
                />

                <Input
                  label="Telefone *"
                  value={phone}
                  onChangeText={(v: string) => setPhone(maskPhoneBR(v))}
                  keyboardType="phone-pad"
                  placeholder="(11) 99999-9999"
                />
              </Section>

                            <Section title="Itens">
                {renderItemsSection()}
              </Section>

              <Section title="Imagens">
                <TouchableOpacity style={s.imageButton} onPress={pickImages}>
                  <Ionicons name="image-outline" size={22} color="#fff" />
                  <Text style={s.imageButtonText}>Adicionar imagens</Text>
                </TouchableOpacity>

                {!!images.length && (
                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={{ gap: 10, marginTop: 10 }}
                  >
                    {images.map((img) => (
                      <View key={img} style={s.imageWrap}>
                        <Image source={{ uri: img }} style={s.image} />
                        <TouchableOpacity style={s.removeImage} onPress={() => removeImage(img)}>
                          <Ionicons name="close" size={16} color="#fff" />
                        </TouchableOpacity>
                      </View>
                    ))}
                  </ScrollView>
                )}
              </Section>

              <Section title="Condições">
                <Input
                  label="Prazo de embarque *"
                  value={deadline}
                  onChangeText={setDeadline}
                  placeholder="Ex: 15 dias úteis"
                />

                <Input
                  label="Condições de pagamento"
                  value={paymentTerms}
                  onChangeText={setPaymentTerms}
                  placeholder="Ex: 30/60/90 dias"
                />

                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Input
                      label="Desconto (R$)"
                      value={discount}
                      onChangeText={(v: string) => setDiscount(maskCurrency(v))}
                      keyboardType="numeric"
                      placeholder="0,00"
                    />
                  </View>

                  <View style={{ flex: 1 }}>
                    <Input
                      label="Validade (dias)"
                      value={validity}
                      onChangeText={(v: string) =>
                        setValidity(v.replace(/\D/g, "").slice(0, 3))
                      }
                      keyboardType="number-pad"
                      placeholder="15"
                    />
                  </View>
                </View>

                <Input
                  label="Observações"
                  value={notes}
                  onChangeText={setNotes}
                  placeholder="Opcional"
                  multiline
                />
              </Section>

              <View style={s.totalBox}>
                <View style={{ flex: 1 }}>
                  <Text style={s.totalLabel}>Subtotal</Text>
                  <Text style={s.subValue}>{formatCurrency(subtotal)}</Text>
                  {discountNum > 0 && (
                    <Text style={s.subValue}>- {formatCurrency(discountNum)} desconto</Text>
                  )}
                </View>

                <View style={{ alignItems: "flex-end" }}>
                  <Text style={s.totalLabel}>Total</Text>
                  <Text style={s.totalValue}>{formatCurrency(total)}</Text>
                </View>
              </View>
            </>
          )}
        </ScrollView>

        {!isDesktop && (
          <View style={s.bottom}>
            <TouchableOpacity
              style={[s.cta, saving && { opacity: 0.7 }]}
              onPress={submit}
              disabled={saving}
            >
              {saving ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Ionicons name="checkmark-circle" size={22} color="#fff" />
                  <Text style={s.ctaText}>
                    {isEditing ? "Salvar alterações" : "Criar proposta"}
                  </Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        )}
      </KeyboardAvoidingView>

      <UpgradeModal
        visible={upgradeOpen}
        message={upgradeMsg}
        onClose={() => setUpgradeOpen(false)}
      />
    </SafeAreaView>
  );
}



function Section({ title, right, children }: any) {
  return (
    <View style={s.section}>
      <View style={s.sectionHead}>
        <Text style={s.sectionTitle}>{title}</Text>
        {right}
      </View>
      <View style={{ gap: 10 }}>{children}</View>
    </View>
  );
}

function Input({ label, customHeight, ...props }: any) {
  console.log("RENDER INPUT", label);
  return (
    <View style={{ gap: 6, width: "100%" }}>
      <Text style={s.label}>{label}</Text>

      <TextInput
  value={props.value}
  onChangeText={props.onChangeText}
  onFocus={(event) => {
    console.log("FOCUS", label);
    props.onFocus?.(event);
  }}
  onBlur={(event) => {
    console.log("BLUR", label);
    props.onBlur?.(event);
  }}
  placeholder={props.placeholder}
  keyboardType={props.keyboardType}
  multiline={props.multiline}
  placeholderTextColor={theme.colors.textMuted}
  style={[
    s.input,
    props.multiline && {
      height: customHeight || 80,
      paddingTop: 12,
      textAlignVertical: "top",
    },
  ]}
/>
    </View>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: theme.colors.bg,
  },
  header: {
    paddingHorizontal: 24,
    paddingTop: 12,
  },
  title: {
    fontSize: 28,
    fontWeight: "800",
    color: theme.colors.text,
  },
  subtitle: {
    fontSize: 13,
    color: theme.colors.textSec,
  },
  scroll: {
    padding: 24,
    paddingBottom: 140,
    gap: 16,
  },
  desktopColumns: {
    flexDirection: "row",
    gap: 20,
    alignItems: "flex-start",
  },
  desktopColumn: {
    flex: 1,
    gap: 20,
    minWidth: 420,
  },
  panelCard: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 20,
    padding: 20,
    gap: 16,
  },
  summaryItem: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 12,
  },
  summaryLabel: {
    color: theme.colors.textSec,
    fontSize: 13,
  },
  summaryValue: {
    color: theme.colors.text,
    fontSize: 16,
    fontWeight: "700",
  },
  section: {
    gap: 10,
  },
  sectionHead: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.textMuted,
    letterSpacing: 1.5,
    textTransform: "uppercase",
  },
  link: {
    color: theme.colors.text,
    fontWeight: "700",
    fontSize: 14,
  },
  label: {
    fontSize: 11,
    color: theme.colors.textMuted,
    fontWeight: "700",
    letterSpacing: 0.5,
    textTransform: "uppercase",
  },
  input: {
    height: 52,
    borderRadius: 12,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    paddingHorizontal: 14,
    fontSize: 16,
    color: theme.colors.text,
  },
    addedProductRow: {
    padding: 12,
    backgroundColor: "#F1F5F9",
    borderRadius: 12,
    marginBottom: 8,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  addedProductTitle: {
    fontSize: 15,
    color: theme.colors.text,
  },
  addedProductDesc: {
    fontSize: 12,
    color: theme.colors.textMuted,
    marginTop: 2,
  },
  addedProductSub: {
    fontSize: 13,
    color: theme.colors.textSec,
    marginTop: 4,
  },
  addedProductTotal: {
    fontSize: 15,
    fontWeight: "700",
    color: theme.colors.text,
  },
  selectorBox: {
    padding: 14,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 14,
    marginBottom: 16,
    gap: 8,
  },
  selectedProductInfo: {
    padding: 8,
    backgroundColor: "#E2E8F0",
    borderRadius: 8,
    marginTop: 4,
  },
  selectedProductText: {
    fontSize: 13,
    color: theme.colors.text,
    fontWeight: "600",
  },
  addButton: {
    height: 52,
    backgroundColor: theme.colors.primary,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  addButtonText: {
    color: "#fff",
    fontWeight: "700",
    fontSize: 14,
  },
  productHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  productHeaderText: {
    fontWeight: "700",
    color: theme.colors.text,
  },
  totalBox: {
    marginTop: 8,
    padding: 20,
    backgroundColor: theme.colors.primary,
    borderRadius: 16,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  totalLabel: {
    color: "#94A3B8",
    fontSize: 11,
    letterSpacing: 1.5,
    textTransform: "uppercase",
    fontWeight: "700",
  },
  totalValue: {
    color: "#fff",
    fontSize: 26,
    fontWeight: "800",
    marginTop: 4,
  },
  subValue: {
    color: "rgba(255,255,255,0.7)",
    fontSize: 14,
    marginTop: 4,
  },
  imageButton: {
    height: 52,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 8,
  },
  imageButtonText: {
    color: "#fff",
    fontWeight: "700",
    fontSize: 15,
  },
  imageWrap: {
    position: "relative",
  },
  image: {
    width: 120,
    height: 120,
    borderRadius: 14,
  },
  removeImage: {
    position: "absolute",
    top: 6,
    right: 6,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: "rgba(0,0,0,0.7)",
    alignItems: "center",
    justifyContent: "center",
  },
  bottom: {
    position: "absolute",
    left: 16,
    right: 16,
    bottom: 16,
  },
  cta: {
    height: 56,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  ctaText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
  },
  catalogList: {
    marginTop: 4,
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: theme.colors.border,
    maxHeight: 200,
    overflow: "hidden",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  catalogItem: {
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#F1F5F9",
  },
  catalogItemText: {
    color: theme.colors.text,
    fontSize: 14,
  },
  tabButton: {
    flex: 1,
    height: 40,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: theme.colors.border,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#F8FAFC",
  },
  tabButtonActive: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  tabButtonText: {
    color: theme.colors.textSec,
    fontWeight: "600",
    fontSize: 12,
  },
  tabButtonTextActive: {
    color: "#fff",
  },
});

