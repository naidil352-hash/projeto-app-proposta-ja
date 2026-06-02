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
import {
  useRouter,
  useLocalSearchParams,
} from "expo-router";

import {
  api,
  formatApiError,
} from "../../src/api";

import {
  theme,
  formatCurrency,
} from "../../src/theme";

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
  name: string;
  quantity: string;
  price: string;
};

export default function NewProposal() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;

  const params = useLocalSearchParams();

  const editId =
    typeof params.editId === "string"
      ? params.editId
      : null;

  const isEditing = !!editId;

  const [clientName, setClientName] =
    useState("");

  const [doc, setDoc] = useState("");

  const [phone, setPhone] =
    useState("");

  const [deadline, setDeadline] =
    useState("");

  const [notes, setNotes] =
    useState("");

  const [discount, setDiscount] =
    useState("");

  const [paymentTerms, setPaymentTerms] =
    useState("");

  const [validity, setValidity] =
    useState("15");
	
  const [images, setImages] =
    useState<string[]>([]);
	
  const [products, setProducts] =
    useState<Product[]>([
      {
        name: "",
        quantity: "",
        price: "",
      },
    ]);

  const [saving, setSaving] =
    useState(false);

  const [
    loadingProposal,
    setLoadingProposal,
  ] = useState(false);

  const [upgradeOpen, setUpgradeOpen] =
    useState(false);

  const [upgradeMsg, setUpgradeMsg] =
    useState<string | undefined>();

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

    setProducts([
      {
        name: "",
        quantity: "",
        price: "",
      },
    ]);
  };

  useEffect(() => {
    if (!editId) {
      reset();
      return;
    }

    const loadProposal = async () => {
      try {
        setLoadingProposal(true);

        const { data } = await api.get(
          `/proposals/${editId}`
        );

        setClientName(
          data.client_name || ""
        );

        setDoc(
          data.client_document || ""
        );

        setPhone(
          data.client_phone || ""
        );

        setDeadline(
          data.shipping_deadline || ""
        );

        setNotes(data.notes || "");

        setDiscount(
          formatCurrencyFromBackend(
            data.discount || ""
          )
        );

        setPaymentTerms(
          data.payment_terms || ""
        );

        setValidity(
          String(
            data.validity_days || 15
          )
        );
		
		        setImages(
          Array.isArray(data.images)
            ? data.images
            : []
        );

        if (
          data.products &&
          data.products.length
        ) {
          setProducts(
            data.products.map(
              (p: any) => ({
                name: p.name || "",
                quantity: String(
                  p.quantity || ""
                ),
                price: formatCurrencyFromBackend(
                  p.price || ""
                ),
              })
            )
          );
        }
      } catch (e) {
        Alert.alert(
          "Erro",
          "Não foi possível carregar proposta"
        );
      } finally {
        setLoadingProposal(false);
      }
    };

    loadProposal();
  }, [editId]);

  const addProduct = () => {
    setProducts([
      ...products,
      {
        name: "",
        quantity: "",
        price: "",
      },
    ]);
  };

  const removeProduct = (
    i: number
  ) => {
    if (products.length === 1)
      return;

    setProducts(
      products.filter(
        (_, idx) => idx !== i
      )
    );
  };

  const updateProduct = (
    i: number,
    key: keyof Product,
    value: string
  ) => {
    setProducts(
      products.map((p, idx) =>
        idx === i
          ? {
              ...p,
              [key]: value,
            }
          : p
      )
    );
  };

  const buildUploadForm = async (
    asset: any
  ) => {
    const form = new FormData();

    if (Platform.OS === "web") {
      const response = await fetch(asset.uri);
      const blob = await response.blob();
      const name =
        asset.fileName ||
        asset.uri?.split("/").pop() ||
        "image.jpg";

      form.append("file", blob, name);
    } else {
      form.append(
        "file",
        {
          uri: asset.uri,
          type: asset.type || "image/jpeg",
          name:
            asset.fileName ||
            "image.jpg",
        } as any
      );
    }

    return form;
  };

  const pickImages =
    async () => {
      try {
        const result =
          await ImagePicker.launchImageLibraryAsync({
            mediaTypes:
              ImagePicker.MediaTypeOptions.Images,
            quality: 0.7,
            allowsMultipleSelection: true,
          });

        if (result.canceled) {
          return;
        }

        setSaving(true);

        const uploaded: string[] = [];

        for (const asset of result.assets) {
          const form = await buildUploadForm(asset);

          const res =
            await api.post(
              "/upload/image",
              form
            );

          uploaded.push(
            res.data.url
          );
        }

        setImages((prev) => [
          ...prev,
          ...uploaded,
        ]);
      } catch (e) {
        Alert.alert(
          "Erro",
          "Falha ao enviar imagens"
        );
      } finally {
        setSaving(false);
      }
    };

  const removeImage =
    (url: string) => {
      setImages((prev) =>
        prev.filter((i) => i !== url)
      );
    };

  const subtotal = products.reduce(
    (acc, p) =>
      acc +
      (parseNumber(
        p.quantity
      ) || 0) *
        (parseCurrency(
          p.price
        ) || 0),
    0
  );

  const discountNum =
    parseCurrency(discount);

  const total = Math.max(
    subtotal - discountNum,
    0
  );

  const submit = async () => {
    if (
      !clientName ||
      !doc ||
      !phone ||
      !deadline
    ) {
      Alert.alert(
        "Atenção",
        "Preencha cliente, CNPJ/CPF, telefone e prazo."
      );

      return;
    }

    const cleanProducts =
      products
        .filter((p) =>
          p.name.trim()
        )
        .map((p) => ({
          name: p.name.trim(),
          quantity:
            parseNumber(
              p.quantity
            ),
          price: parseCurrency(
            p.price
          ),
        }));

    if (!cleanProducts.length) {
      Alert.alert(
        "Atenção",
        "Adicione pelo menos 1 produto."
      );

      return;
    }

    try {
      setSaving(true);

	const payload = {
	client_name:
		clientName.trim(),

	client_document:
		doc.trim(),

	client_phone:
		phone.trim(),

	products: cleanProducts,

	shipping_deadline:
		deadline.trim(),

	notes: notes.trim(),

	discount: discountNum,

	payment_terms:
		paymentTerms.trim(),

	images,

	validity_days:
		parseInt(
		validity || "15",
		10
		) || 15,
	};

      let response;

      if (
        isEditing &&
        editId
      ) {
        response = await api.put(
          `/proposals/${editId}`,
          payload
        );
      } else {
        response = await api.post(
          "/proposals",
          payload
        );
      }

      const data =
        response.data;

      reset();

      router.replace(
        `/proposal/${data.id}`
      );
    } catch (e: any) {
      if (
        e?.response?.status ===
        402
      ) {
        setUpgradeMsg(
          e.response.data
            ?.detail
        );

        setUpgradeOpen(true);
      } else {
        Alert.alert(
          "Erro",
          formatApiError(e)
        );
      }
    } finally {
      setSaving(false);
    }
  };

  if (loadingProposal) {
    return (
      <SafeAreaView
        style={s.root}
      >
        <ActivityIndicator
          style={{
            marginTop: 80,
          }}
          color={
            theme.colors.primary
          }
        />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView
      style={s.root}
      edges={["top"]}
      testID="new-proposal-screen"
    >
      <KeyboardAvoidingView
        behavior={
          Platform.OS === "ios"
            ? "padding"
            : undefined
        }
        style={{ flex: 1 }}
      >
        <View style={s.header}>
          <Text style={s.title}>
            {isEditing
              ? "Editar proposta"
              : "Nova proposta"}
          </Text>

          <Text style={s.subtitle}>
            Preencha rápido e envie
            no WhatsApp
          </Text>
        </View>

        <ScrollView
          contentContainerStyle={
            s.scroll
          }
          keyboardShouldPersistTaps="handled"
        >
          {isDesktop ? (
            <View style={s.desktopColumns}>
              <View style={s.desktopColumn}>
                <View style={s.panelCard}>
                  <Section title="Cliente">
                    <Input
                      label="Nome *"
                      value={clientName}
                      onChangeText={
                        setClientName
                      }
                      placeholder="Nome do cliente"
                    />

                    <Input
                      label="CNPJ / CPF *"
                      value={doc}
                      onChangeText={(
                        v: string
                      ) =>
                        setDoc(
                          maskDocument(v)
                        )
                      }
                      keyboardType="number-pad"
                      placeholder="000.000.000-00"
                    />

                    <Input
                      label="Telefone *"
                      value={phone}
                      onChangeText={(
                        v: string
                      ) =>
                        setPhone(
                          maskPhoneBR(v)
                        )
                      }
                      keyboardType="phone-pad"
                      placeholder="(11) 99999-9999"
                    />
                  </Section>
                </View>

                <View style={s.panelCard}>
                  <Section
                    title="Itens"
                    right={
                      <TouchableOpacity
                        onPress={
                          addProduct
                        }
                      >
                        <Text
                          style={s.link}
                        >
                          + Adicionar
                        </Text>
                      </TouchableOpacity>
                    }
                  >
                    {products.map(
                      (p, i) => (
                        <View
                          key={i}
                          style={s.product}
                        >
                          <View
                            style={
                              s.productHeader
                            }
                          >
                            <Text
                              style={
                                s.productHeaderText
                              }
                            >
                              Item {i + 1}
                            </Text>

                            {products.length >
                              1 && (
                              <TouchableOpacity
                                onPress={() =>
                                  removeProduct(
                                    i
                                  )
                                }
                              >
                                <Ionicons
                                  name="trash-outline"
                                  size={18}
                                  color={
                                    theme
                                      .colors
                                      .danger
                                  }
                                />
                              </TouchableOpacity>
                            )}
                          </View>

                          <Input
                            label="Produto"
                            value={p.name}
                            onChangeText={(
                              v: string
                            ) =>
                              updateProduct(
                                i,
                                "name",
                                v
                              )
                            }
                            placeholder="Nome do produto"
                          />

                          <View
                            style={{
                              flexDirection:
                                "row",
                              gap: 8,
                            }}
                          >
                            <View
                              style={{
                                flex: 1,
                              }}
                            >
                              <Input
                                label="Qtd"
                                value={
                                  p.quantity
                                }
                                onChangeText={(
                                  v: string
                                ) =>
                                  updateProduct(
                                    i,
                                    "quantity",
                                    v.replace(
                                      /[^0-9,.]/g,
                                      ""
                                    )
                                  )
                                }
                                keyboardType="numeric"
                                placeholder="0"
                              />
                            </View>

                            <View
                              style={{
                                flex: 1.4,
                              }}
                            >
                              <Input
                                label="Preço un."
                                value={p.price}
                                onChangeText={(
                                  v: string
                                ) =>
                                  updateProduct(
                                    i,
                                    "price",
                                    maskCurrency(
                                      v
                                    )
                                  )
                                }
                                keyboardType="numeric"
                                placeholder="0,00"
                              />
                            </View>
                          </View>
                        </View>
                      )
                    )}
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
                    <TouchableOpacity
                      style={s.imageButton}
                      onPress={pickImages}
                    >
                      <Ionicons
                        name="image-outline"
                        size={22}
                        color="#fff"
                      />

                      <Text
                        style={s.imageButtonText}
                      >
                        Adicionar imagens
                      </Text>
                    </TouchableOpacity>

                    {!!images.length && (
                      <ScrollView
                        horizontal
                        showsHorizontalScrollIndicator={false}
                        contentContainerStyle={{
                          gap: 10,
                        }}
                      >
                        {images.map((img) => (
                          <View
                            key={img}
                            style={s.imageWrap}
                          >
                            <Image
                              source={{
                                uri: img,
                              }}
                              style={s.image}
                            />
                            <TouchableOpacity
                              style={s.removeImage}
                              onPress={() =>
                                removeImage(
                                  img
                                )
                              }
                            >
                              <Ionicons
                                name="close"
                                size={16}
                                color="#fff"
                              />
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
                      onChangeText={
                        setDeadline
                      }
                      placeholder="Ex: 15 dias úteis"
                    />

                    <Input
                      label="Condições de pagamento"
                      value={paymentTerms}
                      onChangeText={
                        setPaymentTerms
                      }
                      placeholder="Ex: 30/60/90 dias"
                    />

                    <View
                      style={{
                        flexDirection:
                          "row",
                        gap: 8,
                      }}
                    >
                      <View
                        style={{ flex: 1 }}
                      >
                        <Input
                          label="Desconto (R$)"
                          value={discount}
                          onChangeText={(
                            v: string
                          ) =>
                            setDiscount(
                              maskCurrency(v)
                            )
                          }
                          keyboardType="numeric"
                          placeholder="0,00"
                        />
                      </View>

                      <View
                        style={{ flex: 1 }}
                      >
                        <Input
                          label="Validade (dias)"
                          value={validity}
                          onChangeText={(
                            v: string
                          ) =>
                            setValidity(
                              v
                                .replace(
                                  /\D/g,
                                  ""
                                )
                                .slice(
                                  0,
                                  3
                                )
                            )
                          }
                          keyboardType="number-pad"
                          placeholder="15"
                        />
                      </View>
                    </View>

                    <Input
                      label="Observações"
                      value={notes}
                      onChangeText={
                        setNotes
                      }
                      placeholder="Opcional"
                      multiline
                    />
                  </Section>
                </View>

                <TouchableOpacity
                  style={[
                    s.cta,
                    saving && {
                      opacity: 0.7,
                    },
                  ]}
                  onPress={submit}
                  disabled={saving}
                >
                  {saving ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <>
                      <Ionicons
                        name="checkmark-circle"
                        size={22}
                        color="#fff"
                      />

                      <Text
                        style={
                          s.ctaText
                        }
                      >
                        {isEditing
                          ? "Salvar alterações"
                          : "Criar proposta"}
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
                  onChangeText={
                    setClientName
                  }
                  placeholder="Nome do cliente"
                />

                <Input
                  label="CNPJ / CPF *"
                  value={doc}
                  onChangeText={(
                    v: string
                  ) =>
                    setDoc(
                      maskDocument(v)
                    )
                  }
                  keyboardType="number-pad"
                  placeholder="000.000.000-00"
                />

                <Input
                  label="Telefone *"
                  value={phone}
                  onChangeText={(
                    v: string
                  ) =>
                    setPhone(
                      maskPhoneBR(v)
                    )
                  }
                  keyboardType="phone-pad"
                  placeholder="(11) 99999-9999"
                />
              </Section>

              <Section
                title="Itens"
                right={
                  <TouchableOpacity
                    onPress={
                      addProduct
                    }
                  >
                    <Text
                      style={s.link}
                    >
                      + Adicionar
                    </Text>
                  </TouchableOpacity>
                }
              >
                {products.map(
                  (p, i) => (
                    <View
                      key={i}
                      style={s.product}
                    >
                      <View
                        style={
                          s.productHeader
                        }
                      >
                        <Text
                          style={
                            s.productHeaderText
                          }
                        >
                          Item {i + 1}
                        </Text>

                        {products.length >
                          1 && (
                          <TouchableOpacity
                            onPress={() =>
                              removeProduct(
                                i
                              )
                            }
                          >
                            <Ionicons
                              name="trash-outline"
                              size={18}
                              color={
                                theme
                                  .colors
                                  .danger
                              }
                            />
                          </TouchableOpacity>
                        )}
                      </View>

                      <Input
                        label="Produto"
                        value={p.name}
                        onChangeText={(
                          v: string
                        ) =>
                          updateProduct(
                            i,
                            "name",
                            v
                          )
                        }
                        placeholder="Nome do produto"
                      />

                      <View
                        style={{
                          flexDirection:
                            "row",
                          gap: 8,
                        }}
                      >
                        <View
                          style={{
                            flex: 1,
                          }}
                        >
                          <Input
                            label="Qtd"
                            value={
                              p.quantity
                            }
                            onChangeText={(
                              v: string
                            ) =>
                              updateProduct(
                                i,
                                "quantity",
                                v.replace(
                                  /[^0-9,.]/g,
                                  ""
                                )
                              )
                            }
                            keyboardType="numeric"
                            placeholder="0"
                          />
                        </View>

                        <View
                          style={{
                            flex: 1.4,
                          }}
                        >
                          <Input
                            label="Preço un."
                            value={p.price}
                            onChangeText={(
                              v: string
                            ) =>
                              updateProduct(
                                i,
                                "price",
                                maskCurrency(
                                  v
                                )
                              )
                            }
                            keyboardType="numeric"
                            placeholder="0,00"
                          />
                        </View>
                      </View>
                    </View>
                  )
                )}
              </Section>

              <Section title="Imagens">

                <TouchableOpacity
                  style={s.imageButton}
                  onPress={pickImages}
                >
                  <Ionicons
                    name="image-outline"
                    size={22}
                    color="#fff"
                  />

                  <Text
                    style={s.imageButtonText}
                  >
                    Adicionar imagens
                  </Text>
                </TouchableOpacity>

                {!!images.length && (

                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={{
                      gap: 10,
                    }}
                  >

                    {images.map((img) => (

                      <View
                        key={img}
                        style={s.imageWrap}
                      >

                        <Image
                          source={{
                            uri: img,
                          }}
                          style={s.image}
                        />

                        <TouchableOpacity
                          style={s.removeImage}
                          onPress={() =>
                            removeImage(
                              img
                            )
                          }
                        >
                          <Ionicons
                            name="close"
                            size={16}
                            color="#fff"
                          />
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
                  onChangeText={
                    setDeadline
                  }
                  placeholder="Ex: 15 dias úteis"
                />

                <Input
                  label="Condições de pagamento"
                  value={paymentTerms}
                  onChangeText={
                    setPaymentTerms
                  }
                  placeholder="Ex: 30/60/90 dias"
                />

                <View
                  style={{
                    flexDirection:
                      "row",
                    gap: 8,
                  }}
                >
                  <View
                    style={{ flex: 1 }}
                  >
                    <Input
                      label="Desconto (R$)"
                      value={discount}
                      onChangeText={(
                        v: string
                      ) =>
                        setDiscount(
                          maskCurrency(v)
                        )
                      }
                      keyboardType="numeric"
                      placeholder="0,00"
                    />
                  </View>

                  <View
                    style={{ flex: 1 }}
                  >
                    <Input
                      label="Validade (dias)"
                      value={validity}
                      onChangeText={(
                        v: string
                      ) =>
                        setValidity(
                          v
                            .replace(
                              /\D/g,
                              ""
                            )
                            .slice(
                              0,
                              3
                            )
                        )
                      }
                      keyboardType="number-pad"
                      placeholder="15"
                    />
                  </View>
                </View>

                <Input
                  label="Observações"
                  value={notes}
                  onChangeText={
                    setNotes
                  }
                  placeholder="Opcional"
                  multiline
                />
              </Section>

              <View style={s.totalBox}>
                <View
                  style={{ flex: 1 }}
                >
                  <Text
                    style={
                      s.totalLabel
                    }
                  >
                    Subtotal
                  </Text>

                  <Text
                    style={
                      s.subValue
                    }
                  >
                    {formatCurrency(
                      subtotal
                    )}
                  </Text>

                  {discountNum >
                    0 && (
                    <Text
                      style={
                        s.subValue
                      }
                    >
                      -{" "}
                      {formatCurrency(
                        discountNum
                      )}{" "}
                      desconto
                    </Text>
                  )}
                </View>

                <View
                  style={{
                    alignItems:
                      "flex-end",
                  }}
                >
                  <Text
                    style={
                      s.totalLabel
                    }
                  >
                    Total
                  </Text>

                  <Text
                    style={
                      s.totalValue
                    }
                  >
                    {formatCurrency(
                      total
                    )}
                  </Text>
                </View>
              </View>
            </>
          )}
        </ScrollView>

        {!isDesktop && (
          <View style={s.bottom}>
            <TouchableOpacity
              style={[
                s.cta,
                saving && {
                  opacity: 0.7,
                },
              ]}
              onPress={submit}
              disabled={saving}
            >
              {saving ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Ionicons
                    name="checkmark-circle"
                    size={22}
                    color="#fff"
                  />

                  <Text
                    style={
                      s.ctaText
                    }
                  >
                    {isEditing
                      ? "Salvar alterações"
                      : "Criar proposta"}
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
        onClose={() =>
          setUpgradeOpen(false)
        }
      />
    </SafeAreaView>
  );
}

function Section({
  title,
  right,
  children,
}: any) {
  return (
    <View style={s.section}>
      <View style={s.sectionHead}>
        <Text
          style={s.sectionTitle}
        >
          {title}
        </Text>

        {right}
      </View>

      <View style={{ gap: 10 }}>
        {children}
      </View>
    </View>
  );
}

function Input({
  label,
  ...props
}: any) {
  return (
    <View style={{ gap: 6 }}>
      <Text style={s.label}>
        {label}
      </Text>

      <TextInput
        {...props}
        style={[
          s.input,
          props.multiline && {
            height: 80,
            paddingTop: 12,
            textAlignVertical:
              "top",
          },
        ]}
        placeholderTextColor={
          theme.colors.textMuted
        }
      />
    </View>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor:
      theme.colors.bg,
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
    color:
      theme.colors.textSec,
    marginTop: 4,
  },

  scroll: {
    padding: 24,
    paddingBottom: 120,
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
    justifyContent:
      "space-between",
    alignItems: "center",
  },

  sectionTitle: {
    fontSize: 12,
    fontWeight: "700",
    color:
      theme.colors.textMuted,
    letterSpacing: 1.5,
    textTransform:
      "uppercase",
  },

  link: {
    color: theme.colors.text,
    fontWeight: "700",
    fontSize: 14,
  },

  label: {
    fontSize: 11,
    color:
      theme.colors.textMuted,
    fontWeight: "700",
    letterSpacing: 0.5,
    textTransform:
      "uppercase",
  },

  input: {
    height: 52,
    borderRadius: 12,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor:
      theme.colors.border,
    paddingHorizontal: 14,
    fontSize: 16,
    color: theme.colors.text,
  },

  product: {
    padding: 14,
    backgroundColor:
      "#F1F5F9",
    borderRadius: 14,
    gap: 10,
  },

  productHeader: {
    flexDirection: "row",
    justifyContent:
      "space-between",
    alignItems: "center",
  },

  productHeaderText: {
    fontWeight: "700",
    color: theme.colors.text,
  },

  totalBox: {
    marginTop: 8,
    padding: 20,
    backgroundColor:
      theme.colors.primary,
    borderRadius: 16,
    flexDirection: "row",
    justifyContent:
      "space-between",
    alignItems: "center",
  },

  totalLabel: {
    color: "#94A3B8",
    fontSize: 11,
    letterSpacing: 1.5,
    textTransform:
      "uppercase",
    fontWeight: "700",
  },

  totalValue: {
    color: "#fff",
    fontSize: 26,
    fontWeight: "800",
    marginTop: 4,
  },

  subValue: {
    color:
      "rgba(255,255,255,0.7)",
    fontSize: 14,
    marginTop: 4,
  },

  imageButton: {
    height: 52,
    borderRadius: 12,
    backgroundColor:
      theme.colors.primary,
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
    backgroundColor:
      "rgba(0,0,0,0.7)",
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
    backgroundColor:
      theme.colors.primary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent:
      "center",
    gap: 8,
  },

  ctaText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
  },
});